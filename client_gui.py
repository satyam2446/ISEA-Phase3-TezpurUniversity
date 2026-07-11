#!/usr/bin/env python3
"""
client_gui.py
=============
Assignment 6 - GUI-Based Multi-Client Chat Application Using TCP
Tkinter desktop client.

Windows
-------
1. LoginWindow  - username / optional password / Connect / Exit, with
                  validation and success/error dialogs.
2. ChatWindow   - scrollable chat area, online-users panel, message entry,
                  Send button, Disconnect button, status label, timestamps,
                  auto-scroll, resizable layout.

Threading model
---------------
The GUI (Tkinter main loop) must never block on socket I/O. A dedicated
background thread continuously calls socket.recv() and pushes decoded
JSON messages onto a thread-safe queue.Queue. The main thread polls that
queue every 100 ms using root.after(), which is the standard safe pattern
for combining Tkinter with background threads (Tkinter itself is not
thread-safe, so all widget updates happen on the main thread only).

Wire protocol: see server.py docstring. Newline-delimited JSON.
"""

import socket
import threading
import json
import queue
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 55555
BUFFER_SIZE = 4096
POLL_INTERVAL_MS = 100
RECONNECT_TIMEOUT_SEC = 5


def now_time():
    return datetime.now().strftime("%H:%M:%S")


# --------------------------------------------------------------------------
# Networking wrapper used by the GUI
# --------------------------------------------------------------------------
class ChatClientNetwork:
    """
    Encapsulates the raw socket connection and the background receiver
    thread. All incoming server messages are placed on `inbound_queue`
    for the GUI thread to consume via root.after() polling.
    """

    def __init__(self, inbound_queue):
        self.sock = None
        self.inbound_queue = inbound_queue
        self._recv_thread = None
        self._recv_buffer = b""
        self._connected = False

    def connect(self, host, port, timeout=RECONNECT_TIMEOUT_SEC):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((host, port))
        self.sock.settimeout(None)  # blocking mode for the receiver thread
        self._connected = True

    def send_json(self, obj):
        if not self._connected or self.sock is None:
            return False
        try:
            data = (json.dumps(obj) + "\n").encode("utf-8")
            self.sock.sendall(data)
            return True
        except OSError:
            self._connected = False
            return False

    def start_receiving(self):
        self._recv_thread = threading.Thread(target=self._receive_loop, daemon=True, name="ReceiverThread")
        self._recv_thread.start()

    def _receive_loop(self):
        """Runs on a background thread. Never touches Tkinter widgets directly."""
        while self._connected:
            try:
                chunk = self.sock.recv(BUFFER_SIZE)
            except OSError:
                break
            if not chunk:
                break
            self._recv_buffer += chunk
            while b"\n" in self._recv_buffer:
                line, self._recv_buffer = self._recv_buffer.split(b"\n", 1)
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                self.inbound_queue.put(msg)

        self._connected = False
        self.inbound_queue.put({"type": "_CONNECTION_LOST"})

    def close(self):
        self._connected = False
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass

    @property
    def connected(self):
        return self._connected


# --------------------------------------------------------------------------
# Login window
# --------------------------------------------------------------------------
class LoginWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Assignment 6 - Chat Login")
        self.root.geometry("380x330")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e2530")

        self.result = None  # set to dict(username, password, host, port) on success

        container = tk.Frame(root, bg="#1e2530", padx=30, pady=25)
        container.pack(fill="both", expand=True)

        title = tk.Label(
            container, text="TCP Chat Client", font=("Segoe UI", 18, "bold"),
            bg="#1e2530", fg="#ffffff"
        )
        title.pack(pady=(0, 4))

        subtitle = tk.Label(
            container, text="Assignment 6 - Multi-Client Chat", font=("Segoe UI", 9),
            bg="#1e2530", fg="#8b95a5"
        )
        subtitle.pack(pady=(0, 18))

        self._make_field(container, "Username *", "username_entry")
        self._make_field(container, "Password (optional)", "password_entry", show="*")

        host_frame = tk.Frame(container, bg="#1e2530")
        host_frame.pack(fill="x", pady=(6, 0))
        tk.Label(host_frame, text="Server Host", bg="#1e2530", fg="#c7cdd6",
                 font=("Segoe UI", 9)).pack(anchor="w")
        self.host_entry = tk.Entry(host_frame, font=("Segoe UI", 10))
        self.host_entry.insert(0, DEFAULT_HOST)
        self.host_entry.pack(fill="x", pady=(2, 8))

        port_frame = tk.Frame(container, bg="#1e2530")
        port_frame.pack(fill="x")
        tk.Label(port_frame, text="Server Port", bg="#1e2530", fg="#c7cdd6",
                 font=("Segoe UI", 9)).pack(anchor="w")
        self.port_entry = tk.Entry(port_frame, font=("Segoe UI", 10))
        self.port_entry.insert(0, str(DEFAULT_PORT))
        self.port_entry.pack(fill="x", pady=(2, 14))

        btn_frame = tk.Frame(container, bg="#1e2530")
        btn_frame.pack(fill="x", pady=(10, 0))

        connect_btn = tk.Button(
            btn_frame, text="Connect", font=("Segoe UI", 10, "bold"),
            bg="#3d7eff", fg="white", activebackground="#5b91ff",
            relief="flat", padx=10, pady=8, command=self.on_connect
        )
        connect_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        exit_btn = tk.Button(
            btn_frame, text="Exit", font=("Segoe UI", 10, "bold"),
            bg="#3a4353", fg="white", activebackground="#4a5468",
            relief="flat", padx=10, pady=8, command=self.on_exit
        )
        exit_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

        self.username_entry.focus_set()
        self.root.bind("<Return>", lambda e: self.on_connect())
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)

    def _make_field(self, parent, label, attr_name, show=None):
        frame = tk.Frame(parent, bg="#1e2530")
        frame.pack(fill="x", pady=(0, 8))
        tk.Label(frame, text=label, bg="#1e2530", fg="#c7cdd6",
                 font=("Segoe UI", 9)).pack(anchor="w")
        entry = tk.Entry(frame, font=("Segoe UI", 10), show=show)
        entry.pack(fill="x", pady=(2, 0))
        setattr(self, attr_name, entry)

    def on_connect(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        host = self.host_entry.get().strip() or DEFAULT_HOST
        port_raw = self.port_entry.get().strip() or str(DEFAULT_PORT)

        if not username:
            messagebox.showerror("Validation Error", "Username is required.")
            return
        if " " in username or len(username) > 32:
            messagebox.showerror("Validation Error", "Username must not contain spaces and must be <= 32 characters.")
            return
        try:
            port = int(port_raw)
            if not (0 < port < 65536):
                raise ValueError
        except ValueError:
            messagebox.showerror("Validation Error", "Port must be a valid integer between 1 and 65535.")
            return

        self.result = {"username": username, "password": password, "host": host, "port": port}
        self.root.quit()  # release mainloop but keep window object alive for destroy()

    def on_exit(self):
        self.result = None
        self.root.quit()


# --------------------------------------------------------------------------
# Main chat window
# --------------------------------------------------------------------------
class ChatWindow:
    def __init__(self, root, network: ChatClientNetwork, username, host, port):
        self.root = root
        self.network = network
        self.username = username
        self.host = host
        self.port = port

        self.root.title(f"Assignment 6 - Chat ({username})")
        self.root.geometry("880x560")
        self.root.minsize(680, 420)
        self.root.configure(bg="#1e2530")
        self.root.protocol("WM_DELETE_WINDOW", self.on_disconnect)

        self._build_layout()
        self._poll_inbound_queue()

    # ---- UI construction ----------------------------------------------------
    def _build_layout(self):
        # Top status bar
        status_bar = tk.Frame(self.root, bg="#161b24", height=34)
        status_bar.pack(side="top", fill="x")
        self.status_label = tk.Label(
            status_bar, text=f"Connected as {self.username} to {self.host}:{self.port}",
            bg="#161b24", fg="#4caf50", font=("Segoe UI", 9, "bold"), anchor="w"
        )
        self.status_label.pack(side="left", padx=12, pady=6)

        self.clock_label = tk.Label(status_bar, text="", bg="#161b24", fg="#8b95a5",
                                     font=("Segoe UI", 9))
        self.clock_label.pack(side="right", padx=12, pady=6)
        self._tick_clock()

        # Main paned area: chat (left) + users panel (right)
        main_pane = tk.PanedWindow(self.root, orient="horizontal", sashwidth=4,
                                    bg="#1e2530", bd=0)
        main_pane.pack(fill="both", expand=True, padx=8, pady=8)

        # --- Chat area ---
        chat_frame = tk.Frame(main_pane, bg="#1e2530")
        self.chat_area = scrolledtext.ScrolledText(
            chat_frame, wrap="word", state="disabled", font=("Consolas", 10),
            bg="#11151c", fg="#e6e9ef", insertbackground="white", relief="flat",
            padx=10, pady=8
        )
        self.chat_area.pack(fill="both", expand=True)

        # Tag styles for message categories
        self.chat_area.tag_configure("system", foreground="#f5a623", font=("Consolas", 9, "italic"))
        self.chat_area.tag_configure("private", foreground="#c792ea")
        self.chat_area.tag_configure("own", foreground="#4caf50")
        self.chat_area.tag_configure("other", foreground="#82aaff")
        self.chat_area.tag_configure("error", foreground="#ff5370")
        self.chat_area.tag_configure("timestamp", foreground="#5c6473")

        main_pane.add(chat_frame, stretch="always")

        # --- Users panel ---
        users_frame = tk.Frame(main_pane, bg="#161b24", width=190)
        tk.Label(users_frame, text="ONLINE USERS", bg="#161b24", fg="#8b95a5",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        self.users_listbox = tk.Listbox(
            users_frame, bg="#11151c", fg="#e6e9ef", relief="flat",
            font=("Segoe UI", 10), highlightthickness=0, selectbackground="#3d7eff"
        )
        self.users_listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.users_listbox.bind("<Double-Button-1>", self._on_user_double_click)

        refresh_btn = tk.Button(
            users_frame, text="Refresh List", command=self.request_user_list,
            bg="#3a4353", fg="white", relief="flat", font=("Segoe UI", 9)
        )
        refresh_btn.pack(fill="x", padx=10, pady=(0, 10))

        main_pane.add(users_frame, stretch="never")

        # --- Input area ---
        input_frame = tk.Frame(self.root, bg="#1e2530")
        input_frame.pack(side="bottom", fill="x", padx=8, pady=(0, 8))

        tk.Label(input_frame, text="To:", bg="#1e2530", fg="#c7cdd6",
                 font=("Segoe UI", 9)).pack(side="left", padx=(2, 4))
        self.target_var = tk.StringVar(value="Everyone")
        self.target_menu = ttk.Combobox(
            input_frame, textvariable=self.target_var, values=["Everyone"],
            width=14, state="readonly"
        )
        self.target_menu.pack(side="left", padx=(0, 8))

        self.message_entry = tk.Entry(input_frame, font=("Segoe UI", 11))
        self.message_entry.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=6)
        self.message_entry.bind("<Return>", lambda e: self.send_message())
        self.message_entry.focus_set()

        send_btn = tk.Button(
            input_frame, text="Send", font=("Segoe UI", 10, "bold"),
            bg="#3d7eff", fg="white", relief="flat", padx=18,
            command=self.send_message
        )
        send_btn.pack(side="left", padx=(0, 6))

        disconnect_btn = tk.Button(
            input_frame, text="Disconnect", font=("Segoe UI", 10, "bold"),
            bg="#c0392b", fg="white", relief="flat", padx=12,
            command=self.on_disconnect
        )
        disconnect_btn.pack(side="left")

        # Kick off an initial user-list request once the socket is ready.
        self.root.after(300, self.request_user_list)

    def _tick_clock(self):
        self.clock_label.config(text=datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    # ---- helpers --------------------------------------------------------------
    def _append_chat(self, text, tag=None):
        self.chat_area.configure(state="normal")
        if tag:
            self.chat_area.insert("end", text + "\n", tag)
        else:
            self.chat_area.insert("end", text + "\n")
        self.chat_area.configure(state="disabled")
        self.chat_area.see("end")  # auto-scroll to bottom

    def _on_user_double_click(self, event):
        selection = self.users_listbox.curselection()
        if selection:
            name = self.users_listbox.get(selection[0])
            if name != self.username:
                self.target_var.set(name)

    def request_user_list(self):
        self.network.send_json({"type": "LIST"})

    # ---- outbound actions -------------------------------------------------
    def send_message(self):
        text = self.message_entry.get().strip()
        if not text:
            return
        target = self.target_var.get()

        if target == "Everyone":
            ok = self.network.send_json({"type": "MESSAGE", "text": text})
            if ok:
                self._append_chat(f"[{now_time()}] You (broadcast): {text}", tag="own")
        else:
            ok = self.network.send_json({"type": "PRIVATE", "to": target, "text": text})
            # Server echoes private messages back, so we do not print locally
            # to avoid duplicate lines; if the send failed, warn the user.
            if not ok:
                self._append_chat(f"[{now_time()}] (!) Failed to send private message.", tag="error")

        if not ok:
            self._append_chat(f"[{now_time()}] (!) Connection lost. Message not sent.", tag="error")

        self.message_entry.delete(0, "end")

    def on_disconnect(self):
        try:
            self.network.send_json({"type": "DISCONNECT"})
        except Exception:
            pass
        self.network.close()
        self.root.destroy()

    # ---- inbound message handling (runs on the GUI/main thread) -----------
    def _poll_inbound_queue(self):
        try:
            while True:
                msg = self.inbound_queue.get_nowait()
                self._handle_inbound(msg)
        except queue.Empty:
            pass
        self.root.after(POLL_INTERVAL_MS, self._poll_inbound_queue)

    def _handle_inbound(self, msg):
        msg_type = msg.get("type")

        if msg_type == "BROADCAST":
            sender = msg.get("sender", "?")
            text = msg.get("text", "")
            ts = msg.get("timestamp", now_time())
            tag = "own" if sender == self.username else "other"
            if sender != self.username:
                self._append_chat(f"[{ts}] {sender}: {text}", tag=tag)

        elif msg_type == "PRIVATE":
            sender = msg.get("sender", "?")
            to = msg.get("to", "?")
            text = msg.get("text", "")
            ts = msg.get("timestamp", now_time())
            if sender == self.username:
                self._append_chat(f"[{ts}] You -> {to} (private): {text}", tag="private")
            else:
                self._append_chat(f"[{ts}] {sender} -> you (private): {text}", tag="private")

        elif msg_type == "SYSTEM":
            text = msg.get("text", "")
            ts = msg.get("timestamp", now_time())
            self._append_chat(f"[{ts}] * {text}", tag="system")
            self.request_user_list()

        elif msg_type == "LIST_RESPONSE":
            users = msg.get("users", [])
            self.users_listbox.delete(0, "end")
            for u in users:
                label = f"{u} (you)" if u == self.username else u
                self.users_listbox.insert("end", u if u != self.username else label)
            targets = ["Everyone"] + [u for u in users if u != self.username]
            self.target_menu["values"] = targets

        elif msg_type == "ERROR":
            self._append_chat(f"[{now_time()}] (!) Server error: {msg.get('text')}", tag="error")

        elif msg_type == "_CONNECTION_LOST":
            self.status_label.config(text="Disconnected from server", fg="#ff5370")
            self._append_chat(f"[{now_time()}] (!) Connection to server lost.", tag="error")
            messagebox.showwarning("Connection Lost", "The connection to the server was lost.")

    @property
    def inbound_queue(self):
        return self.network.inbound_queue

    def display_history(self, history_rows):
        if not history_rows:
            return
        self._append_chat("---- Last messages from previous session ----", tag="system")
        for row in history_rows:
            ts = row.get("timestamp", "")
            sender = row.get("sender", "")
            receiver = row.get("receiver", "")
            mtype = row.get("message_type", "")
            message = row.get("message", "")
            if mtype in ("JOIN", "LEAVE"):
                self._append_chat(f"[{ts}] * {message}", tag="system")
            elif mtype == "PRIVATE":
                self._append_chat(f"[{ts}] {sender} -> {receiver} (private): {message}", tag="private")
            else:
                self._append_chat(f"[{ts}] {sender}: {message}", tag="other")
        self._append_chat("---- End of history ----", tag="system")


# --------------------------------------------------------------------------
# Application bootstrap
# --------------------------------------------------------------------------
def run_login_flow():
    """
    Shows the login window (using .mainloop()/.quit() so the same Tk root
    can be reused), performs the AUTH handshake synchronously (with a
    short timeout) BEFORE opening the main chat window, and returns the
    connected ChatClientNetwork + auth response on success.
    """
    while True:
        login_root = tk.Tk()
        login = LoginWindow(login_root)
        login_root.mainloop()

        if login.result is None:
            login_root.destroy()
            return None  # user chose Exit

        creds = login.result
        login_root.destroy()

        inbound_queue = queue.Queue()
        network = ChatClientNetwork(inbound_queue)
        try:
            network.connect(creds["host"], creds["port"])
        except (OSError, socket.timeout) as exc:
            messagebox.showerror("Connection Failed", f"Could not connect to {creds['host']}:{creds['port']}\n\n{exc}")
            continue

        # Perform AUTH handshake with a bounded wait so a bad/duplicate
        # username shows an error dialog instead of hanging.
        network.send_json({
            "type": "AUTH",
            "username": creds["username"],
            "password": creds["password"],
        })

        network.sock.settimeout(RECONNECT_TIMEOUT_SEC)
        auth_response = _read_one_json(network)
        network.sock.settimeout(None)

        if auth_response is None:
            messagebox.showerror("Connection Failed", "No response from server (timeout).")
            network.close()
            continue

        if auth_response.get("type") == "AUTH_FAIL":
            messagebox.showerror("Authentication Failed", auth_response.get("reason", "Unknown reason."))
            network.close()
            continue

        if auth_response.get("type") == "AUTH_OK":
            messagebox.showinfo("Connected", f"Successfully connected as '{creds['username']}'!")
            return network, creds, auth_response.get("history", [])

        messagebox.showerror("Connection Failed", "Unexpected server response during authentication.")
        network.close()
        continue


def _read_one_json(network: ChatClientNetwork):
    """Blocking helper used only during the synchronous AUTH handshake."""
    buffer = b""
    try:
        while b"\n" not in buffer:
            chunk = network.sock.recv(BUFFER_SIZE)
            if not chunk:
                return None
            buffer += chunk
        line, _ = buffer.split(b"\n", 1)
        return json.loads(line.decode("utf-8"))
    except (OSError, socket.timeout, json.JSONDecodeError):
        return None


def main():
    login_result = run_login_flow()
    if login_result is None:
        return  # user exited from login window

    network, creds, history = login_result
    network.start_receiving()

    chat_root = tk.Tk()
    chat_window = ChatWindow(chat_root, network, creds["username"], creds["host"], creds["port"])
    chat_window.display_history(history)
    chat_root.mainloop()


if __name__ == "__main__":
    main()
