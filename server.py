#!/usr/bin/env python3
"""
server.py
=========
Assignment 6 - GUI-Based Multi-Client Chat Application Using TCP
Production-quality multi-threaded TCP chat server.

Features
--------
- Multiple simultaneous clients (one thread per client)
- Username authentication with duplicate-username prevention
- Join / leave notifications broadcast to all connected clients
- Broadcast messaging ("send to everyone")
- Private messaging ("send to one user")
- /list command support (also available as a structured LIST request from GUI)
- Online user tracking (thread-safe)
- Persistent chat history logging to chat_history.csv
- Event/audit logging to server_events.log via the `logging` module
- Thread-safe client management using a re-entrant lock
- Graceful disconnect handling (both client-initiated and network failure)
- Robust error handling around every socket operation
- Live server statistics (connections, messages, uptime) printed on shutdown
  and periodically written to the log file

Wire Protocol
-------------
All messages exchanged between client and server are UTF-8 encoded JSON
objects, one per line (newline-delimited JSON). This keeps the protocol
simple, human-readable in Wireshark's "Follow TCP Stream" view, and easy
to extend.

Client -> Server message types:
    AUTH        {"type": "AUTH", "username": str, "password": str}
    MESSAGE     {"type": "MESSAGE", "text": str}                  (broadcast)
    PRIVATE     {"type": "PRIVATE", "to": str, "text": str}       (private)
    LIST        {"type": "LIST"}
    DISCONNECT  {"type": "DISCONNECT"}

Server -> Client message types:
    AUTH_OK         {"type": "AUTH_OK", "username": str, "history": [...]}
    AUTH_FAIL       {"type": "AUTH_FAIL", "reason": str}
    BROADCAST       {"type": "BROADCAST", "sender": str, "text": str, "timestamp": str}
    PRIVATE         {"type": "PRIVATE", "sender": str, "to": str, "text": str, "timestamp": str}
    SYSTEM          {"type": "SYSTEM", "text": str, "timestamp": str}
    LIST_RESPONSE   {"type": "LIST_RESPONSE", "users": [str, ...]}
    ERROR           {"type": "ERROR", "text": str}
"""

import socket
import threading
import json
import csv
import logging
import os
import time
import argparse
from datetime import datetime

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 55555
LISTEN_BACKLOG = 20
BUFFER_SIZE = 4096
CHAT_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_history.csv")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_events.log")
HISTORY_REPLAY_COUNT = 5
STATS_LOG_INTERVAL_SEC = 60

# --------------------------------------------------------------------------
# Logging setup
# --------------------------------------------------------------------------
logger = logging.getLogger("ChatServer")
logger.setLevel(logging.DEBUG)

_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(threadName)-15s | %(message)s"
)
_file_handler.setFormatter(_file_formatter)
logger.addHandler(_file_handler)

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(_file_formatter)
logger.addHandler(_console_handler)


def now_iso():
    """Return the current timestamp formatted for display / CSV logging."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# Chat history persistence (CSV)
# --------------------------------------------------------------------------
class ChatHistory:
    """
    Thread-safe wrapper around chat_history.csv.
    Columns: timestamp,sender,receiver,message_type,message
    """

    FIELDNAMES = ["timestamp", "sender", "receiver", "message_type", "message"]

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.path) or os.path.getsize(self.path) == 0:
            with open(self.path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                writer.writeheader()

    def append(self, sender, receiver, message_type, message):
        with self._lock:
            with open(self.path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                writer.writerow({
                    "timestamp": now_iso(),
                    "sender": sender,
                    "receiver": receiver,
                    "message_type": message_type,
                    "message": message,
                })

    def last_n(self, n=HISTORY_REPLAY_COUNT):
        """Return the last n rows (excluding header) as a list of dicts."""
        with self._lock:
            if not os.path.exists(self.path):
                return []
            with open(self.path, "r", newline="", encoding="utf-8") as f:
                reader = list(csv.DictReader(f))
            return reader[-n:] if len(reader) > n else reader


# --------------------------------------------------------------------------
# Server statistics
# --------------------------------------------------------------------------
class ServerStats:
    def __init__(self):
        self._lock = threading.Lock()
        self.start_time = time.time()
        self.total_connections = 0
        self.current_connections = 0
        self.broadcast_count = 0
        self.private_count = 0
        self.auth_failures = 0
        self.total_bytes_received = 0

    def on_connect(self):
        with self._lock:
            self.total_connections += 1
            self.current_connections += 1

    def on_disconnect(self):
        with self._lock:
            self.current_connections = max(0, self.current_connections - 1)

    def on_broadcast(self):
        with self._lock:
            self.broadcast_count += 1

    def on_private(self):
        with self._lock:
            self.private_count += 1

    def on_auth_failure(self):
        with self._lock:
            self.auth_failures += 1

    def on_bytes(self, n):
        with self._lock:
            self.total_bytes_received += n

    def snapshot(self):
        with self._lock:
            uptime = time.time() - self.start_time
            return {
                "uptime_sec": round(uptime, 2),
                "total_connections": self.total_connections,
                "current_connections": self.current_connections,
                "broadcast_count": self.broadcast_count,
                "private_count": self.private_count,
                "auth_failures": self.auth_failures,
                "total_bytes_received": self.total_bytes_received,
            }

    def report_string(self):
        s = self.snapshot()
        return (
            "\n"
            "==================== SERVER STATISTICS ====================\n"
            f" Uptime                : {s['uptime_sec']} seconds\n"
            f" Total connections     : {s['total_connections']}\n"
            f" Currently connected   : {s['current_connections']}\n"
            f" Broadcast messages    : {s['broadcast_count']}\n"
            f" Private messages      : {s['private_count']}\n"
            f" Auth failures         : {s['auth_failures']}\n"
            f" Total bytes received  : {s['total_bytes_received']}\n"
            "============================================================\n"
        )


# --------------------------------------------------------------------------
# Client handler thread
# --------------------------------------------------------------------------
class ClientHandler(threading.Thread):
    def __init__(self, conn, addr, server):
        super().__init__(daemon=True)
        self.conn = conn
        self.addr = addr
        self.server = server
        self.username = None
        self._recv_buffer = b""
        self._alive = True

    # ---- low level helpers -------------------------------------------------
    def send_json(self, obj):
        """Send a JSON object terminated with a newline. Thread-safe per-socket."""
        try:
            data = (json.dumps(obj) + "\n").encode("utf-8")
            self.conn.sendall(data)
            return True
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            logger.warning("Failed to send to %s: %s", self.username or self.addr, exc)
            return False

    def _read_line(self):
        """Read one newline-delimited JSON message, or None on disconnect."""
        while b"\n" not in self._recv_buffer:
            try:
                chunk = self.conn.recv(BUFFER_SIZE)
            except (ConnectionResetError, OSError):
                return None
            if not chunk:
                return None
            self.server.stats.on_bytes(len(chunk))
            self._recv_buffer += chunk
        line, self._recv_buffer = self._recv_buffer.split(b"\n", 1)
        return line

    # ---- main thread loop ---------------------------------------------------
    def run(self):
        self.server.stats.on_connect()
        logger.info("New connection from %s", self.addr)
        try:
            if not self._authenticate():
                return
            self._message_loop()
        except Exception as exc:  # pragma: no cover - defensive catch-all
            logger.error("Unhandled exception for %s: %s", self.addr, exc)
        finally:
            self._cleanup()

    def _authenticate(self):
        raw = self._read_line()
        if raw is None:
            logger.info("Client %s disconnected before authenticating", self.addr)
            return False
        try:
            msg = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json({"type": "ERROR", "text": "Malformed authentication request."})
            return False

        if msg.get("type") != "AUTH":
            self.send_json({"type": "AUTH_FAIL", "reason": "Expected AUTH message first."})
            return False

        username = (msg.get("username") or "").strip()
        password = msg.get("password", "")

        if not username:
            self.send_json({"type": "AUTH_FAIL", "reason": "Username cannot be empty."})
            self.server.stats.on_auth_failure()
            return False

        if len(username) > 32 or any(c.isspace() for c in username):
            self.send_json({"type": "AUTH_FAIL", "reason": "Invalid username format."})
            self.server.stats.on_auth_failure()
            return False

        added = self.server.add_client(username, self)
        if not added:
            self.send_json({"type": "AUTH_FAIL", "reason": f"Username '{username}' is already taken."})
            self.server.stats.on_auth_failure()
            logger.warning("Duplicate username rejected: %s from %s", username, self.addr)
            return False

        self.username = username
        history = self.server.history.last_n(HISTORY_REPLAY_COUNT)
        self.send_json({"type": "AUTH_OK", "username": username, "history": history})
        logger.info("User authenticated: %s from %s", username, self.addr)

        join_text = f"{username} has joined the chat."
        self.server.history.append("SERVER", "ALL", "JOIN", join_text)
        self.server.broadcast(
            {"type": "SYSTEM", "text": join_text, "timestamp": now_iso()},
            exclude=None,
        )
        return True

    def _message_loop(self):
        while self._alive:
            raw = self._read_line()
            if raw is None:
                break
            try:
                msg = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_json({"type": "ERROR", "text": "Malformed message (invalid JSON)."})
                continue

            msg_type = msg.get("type")

            if msg_type == "MESSAGE":
                self._handle_broadcast(msg)
            elif msg_type == "PRIVATE":
                self._handle_private(msg)
            elif msg_type == "LIST":
                self._handle_list()
            elif msg_type == "DISCONNECT":
                logger.info("User %s requested disconnect", self.username)
                break
            else:
                self.send_json({"type": "ERROR", "text": f"Unknown message type: {msg_type}"})

    def _handle_broadcast(self, msg):
        text = str(msg.get("text", "")).strip()
        if not text:
            return
        self.server.stats.on_broadcast()
        self.server.history.append(self.username, "ALL", "BROADCAST", text)
        self.server.broadcast(
            {
                "type": "BROADCAST",
                "sender": self.username,
                "text": text,
                "timestamp": now_iso(),
            },
            exclude=None,
        )
        logger.debug("[BROADCAST] %s: %s", self.username, text)

    def _handle_private(self, msg):
        to_user = str(msg.get("to", "")).strip()
        text = str(msg.get("text", "")).strip()
        if not to_user or not text:
            return

        target = self.server.get_client(to_user)
        if target is None:
            self.send_json({"type": "ERROR", "text": f"User '{to_user}' is not online."})
            return

        self.server.stats.on_private()
        self.server.history.append(self.username, to_user, "PRIVATE", text)

        payload = {
            "type": "PRIVATE",
            "sender": self.username,
            "to": to_user,
            "text": text,
            "timestamp": now_iso(),
        }
        target.send_json(payload)
        # Echo back to sender so their own GUI shows the sent message.
        if to_user != self.username:
            self.send_json(payload)
        logger.debug("[PRIVATE] %s -> %s: %s", self.username, to_user, text)

    def _handle_list(self):
        users = self.server.list_usernames()
        self.send_json({"type": "LIST_RESPONSE", "users": users})

    def _cleanup(self):
        self._alive = False
        if self.username:
            self.server.remove_client(self.username)
            leave_text = f"{self.username} has left the chat."
            self.server.history.append("SERVER", "ALL", "LEAVE", leave_text)
            self.server.broadcast(
                {"type": "SYSTEM", "text": leave_text, "timestamp": now_iso()},
                exclude=None,
            )
            logger.info("User disconnected: %s", self.username)
        try:
            self.conn.close()
        except OSError:
            pass
        self.server.stats.on_disconnect()


# --------------------------------------------------------------------------
# Chat server
# --------------------------------------------------------------------------
class ChatServer:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.clients = {}          # username -> ClientHandler
        self._clients_lock = threading.RLock()
        self.history = ChatHistory(CHAT_HISTORY_FILE)
        self.stats = ServerStats()
        self._server_socket = None
        self._running = False

    # ---- client registry (thread-safe) -------------------------------------
    def add_client(self, username, handler):
        with self._clients_lock:
            if username in self.clients:
                return False
            self.clients[username] = handler
            return True

    def remove_client(self, username):
        with self._clients_lock:
            self.clients.pop(username, None)

    def get_client(self, username):
        with self._clients_lock:
            return self.clients.get(username)

    def list_usernames(self):
        with self._clients_lock:
            return sorted(self.clients.keys())

    def broadcast(self, obj, exclude=None):
        with self._clients_lock:
            targets = [c for name, c in self.clients.items() if name != exclude]
        for client in targets:
            client.send_json(obj)

    # ---- stats logger thread ------------------------------------------------
    def _stats_logger_loop(self):
        while self._running:
            time.sleep(STATS_LOG_INTERVAL_SEC)
            if self._running:
                logger.info("Periodic stats: %s", self.stats.snapshot())

    # ---- main server loop ---------------------------------------------------
    def start(self):
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(LISTEN_BACKLOG)
        self._running = True

        logger.info("Chat server listening on %s:%s", self.host, self.port)
        print(f"[SERVER] Listening on {self.host}:{self.port} (Ctrl+C to stop)")

        threading.Thread(target=self._stats_logger_loop, daemon=True, name="StatsLogger").start()

        try:
            while self._running:
                try:
                    conn, addr = self._server_socket.accept()
                except OSError:
                    break
                handler = ClientHandler(conn, addr, self)
                handler.name = f"Client-{addr[0]}:{addr[1]}"
                handler.start()
        except KeyboardInterrupt:
            print("\n[SERVER] Shutdown requested (Ctrl+C).")
        finally:
            self.shutdown()

    def shutdown(self):
        self._running = False
        with self._clients_lock:
            for handler in list(self.clients.values()):
                handler.send_json({"type": "SYSTEM", "text": "Server is shutting down.", "timestamp": now_iso()})
                try:
                    handler.conn.close()
                except OSError:
                    pass
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
        logger.info("Server shutdown complete.")
        print(self.stats.report_string())
        logger.info(self.stats.report_string())


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Assignment 6 - Multi-client TCP chat server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host/IP to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind (default: 55555)")
    args = parser.parse_args()

    server = ChatServer(host=args.host, port=args.port)
    server.start()


if __name__ == "__main__":
    main()
