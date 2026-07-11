 GUI-Based Multi-Client Chat Application Using TCP

A production-quality, multi-threaded TCP chat system with a Tkinter desktop
client. Built with raw Python sockets, threading, and a lightweight
newline-delimited JSON protocol — no external networking frameworks.

---

## 1. Objective

Design and implement a multi-client chat application consisting of:

- A **multi-threaded TCP server** (`server.py`) that authenticates users,
  tracks who is online, relays broadcast and private messages, logs every
  event, and reports live statistics.
- A **Tkinter GUI client** (`client_gui.py`) with a login screen and a main
  chat window that stays responsive at all times by receiving network data
  on a background thread.
- Supporting tooling to measure performance under load and generate graphs
  (`generate_graphs.py`), plus full documentation for testing with
  **Mininet** and **Wireshark**.

---

## 2. Requirements

| Requirement        | Version / Notes                                   |
|---------------------|----------------------------------------------------|
| Python              | 3.9 or newer                                       |
| tkinter             | Bundled with Python on Windows/macOS. On Linux: `sudo apt install python3-tk` |
| pandas              | `>= 2.0.0` (see `requirements.txt`)                |
| matplotlib          | `>= 3.7.0` (see `requirements.txt`)                |
| Mininet             | Optional — for emulated multi-host network testing |
| Wireshark           | Optional — for packet capture verification         |

---

## 3. Folder Structure

```
assignment6/
├── server.py                      # Multi-threaded TCP chat server
├── client_gui.py                  # Tkinter GUI chat client
├── generate_graphs.py             # Builds performance graphs from CSV data
├── requirements.txt                # Python dependencies (pandas, matplotlib)
├── README.md                       # This file
├── REPORT.md                       # Full academic report (see structure below)
├── .gitignore                      # Git ignore rules
├── chat_history.csv                # Sample/demo persisted chat log
├── performance_results.csv         # Sample/demo performance test results
├── server_events.log               # Sample/demo server event log
├── graphs/
│   ├── clients_vs_delay.png
│   ├── clients_vs_throughput.png
│   └── message_type_distribution.png
└── screenshots/
    └── (place required screenshots here — see Section 8 of REPORT.md)
```

---

## 4. Installation

```bash
# 1. Clone or extract the project
cd assignment6

# 2. (Recommended) create a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Linux only — install Tkinter if not already present
sudo apt install python3-tk
```

---

## 5. Execution

### 5.1 Start the server

```bash
python3 server.py --host 0.0.0.0 --port 55555
```

`--host` and `--port` are optional; they default to `0.0.0.0:55555`.
The server prints its listening address and writes detailed events to
`server_events.log`. Press **Ctrl+C** to shut it down gracefully — it will
notify all connected clients and print final statistics.

### 5.2 Launch one or more clients

In separate terminals (or on separate machines/VMs pointed at the server's
IP):

```bash
python3 client_gui.py
```

1. Enter a **username** (required, no spaces, ≤ 32 characters).
2. Optionally enter a **password** (not currently validated server-side —
   reserved for future extension; see REPORT.md §4).
3. Confirm/edit the **Server Host** and **Server Port** fields.
4. Click **Connect**. A success dialog confirms authentication; an error
   dialog appears immediately if the username is already taken or the
   server is unreachable.
5. In the chat window: pick **Everyone** or a specific username from the
   **To:** dropdown, type a message, and press **Enter** or click **Send**.
   Double-clicking a name in the **Online Users** panel selects it as the
   private-message target.
6. Click **Disconnect** (or close the window) to leave cleanly.

### 5.3 Generate performance graphs

Run real load tests (see §6) to populate `performance_results.csv`, or use
the provided sample data, then run:

```bash
python3 generate_graphs.py
```

This creates/overwrites the three PNGs inside `graphs/`.

---

## 6. Testing

### 6.1 Functional test checklist

| # | Test case                                            | Expected result                                  |
|---|-------------------------------------------------------|---------------------------------------------------|
| 1 | Connect with a fresh username                         | `AUTH_OK`, success dialog, chat window opens       |
| 2 | Connect again with the **same** username from another client | `AUTH_FAIL`, error dialog, connection closed |
| 3 | Client A sends a broadcast message                     | All other connected clients see it instantly       |
| 4 | Client A sends a private message to Client B           | Only B (and A, as an echo) receives it             |
| 5 | Client joins                                            | All other clients see a "has joined" system message |
| 6 | Client disconnects (graceful or by closing window)      | All others see a "has left" system message; server removes them from `/list` |
| 7 | Click **Refresh List** / reconnect                      | Online users panel updates correctly               |
| 8 | Reconnect after a previous session                       | Last 5 messages from `chat_history.csv` are replayed at the top of the chat window |
| 9 | Kill the server while a client is connected              | Client GUI shows "Connection Lost" warning, does not crash |

This exact sequence (steps 1–9) was exercised against a live instance of
`server.py` during development using a scripted socket harness that
performs the same JSON handshake as `client_gui.py`, confirming that
authentication, duplicate-name rejection, broadcast delivery, private
delivery, and the `/list`-equivalent `LIST` request all behave as
specified above.

### 6.2 Load / performance testing

Use multiple terminal clients (or a scripted test harness) connecting
simultaneously, sending a fixed number of messages each, and record:

- **Average delay** — round-trip time between sending a broadcast and
  every other client receiving it (in milliseconds).
- **Throughput** — total messages processed by the server per second.
- **Broadcast count** / **Private count** — totals per test run.

Append one row per test run to `performance_results.csv` using this
schema:

```
num_clients,avg_delay_ms,throughput_msgs_per_sec,broadcast_count,private_count
```

Then run `python3 generate_graphs.py` to visualize the results.

### 6.3 Testing over Mininet

Mininet lets you emulate a multi-host network on a single Linux machine so
you can test the chat system across "different machines" without needing
physical hardware.

```bash
# Launch a simple 1-switch, N-host topology (adjust host count as needed)
sudo mn --topo single,4 --mac --controller default

# Inside the Mininet CLI, open terminals on individual hosts:
mininet> xterm h1 h2 h3 h4

# On h1 (acts as the server):
python3 server.py --host 0.0.0.0 --port 55555

# On h2, h3, h4 (acts as clients) — use h1's Mininet IP, e.g. 10.0.0.1:
python3 client_gui.py
```

Useful Mininet commands during testing:

```bash
mininet> nodes                 # list all nodes
mininet> net                   # show network links
mininet> h1 ifconfig           # show h1's IP address
mininet> pingall                # verify connectivity between all hosts
mininet> h2 ping -c 4 h1        # verify h2 can reach the server host
```

---

## 7. Wireshark Verification

Capture on the network interface Mininet uses (e.g. `s1-eth1`) or your
loopback/Ethernet interface for a local test, then apply this display
filter to isolate chat traffic:

```
tcp.port == 55555
```

What to look for:

| Event                        | What to observe in Wireshark                                             |
|-------------------------------|----------------------------------------------------------------------------|
| **TCP 3-way handshake**       | `SYN` → `SYN, ACK` → `ACK` between client and server on connect            |
| **Authentication**            | A `PSH, ACK` packet from client to server containing the `AUTH` JSON payload, followed by the server's `AUTH_OK`/`AUTH_FAIL` response |
| **Broadcast packets**         | One `PSH, ACK` packet from the sending client, followed by *N* separate `PSH, ACK` packets from the server — one to each other connected client (fan-out is visible as multiple packets with the same payload leaving the server in quick succession) |
| **Private packets**           | A single `PSH, ACK` from sender to server, followed by exactly one server-to-recipient `PSH, ACK` (and one echo back to the sender) |
| **Client disconnect / TCP FIN** | `FIN, ACK` from the disconnecting client, `ACK` from the server, then `FIN, ACK` from the server, final `ACK` from the client (standard 4-way TCP termination) |
| **ACKs**                      | Pure `ACK` packets acknowledging each JSON message, distinguishable from `PSH, ACK` data packets |

Capture steps:

1. Start Wireshark, select the correct interface, apply `tcp.port == 55555`.
2. Start `server.py`.
3. Connect a client — capture the handshake + `AUTH` exchange.
4. Send a broadcast message with 2+ clients connected — capture the fan-out.
5. Send a private message — capture the single targeted delivery.
6. Disconnect a client — capture the FIN/ACK termination sequence.
7. Use **Statistics → Conversations** to confirm one persistent TCP stream
   per connected client, and **Follow → TCP Stream** to read the JSON
   payloads in plaintext (this project intentionally does not encrypt
   traffic, matching the assignment's networking-focus scope).

---

## 8. Screenshots

See `screenshots/` and `REPORT.md` §8 for the full list of required
screenshots (login window, successful connection, chat window, broadcast
messaging, private messaging, online users, join/leave notifications,
Wireshark handshake/broadcast/private/termination captures, and the three
generated graphs). Add your captured `.png` files to that folder using the
exact filenames referenced in the report before submission.

---

## 9. GitHub

### Suggested repository structure

Identical to the folder structure in §3 above — the project is already
laid out as a ready-to-push repository root.

### Suggested commit messages

```
Initial commit: project scaffolding and requirements
feat(server): implement multi-threaded TCP server with auth and broadcast
feat(server): add private messaging, /list, and CSV chat history logging
feat(server): add thread-safe client registry and graceful shutdown stats
feat(client): implement Tkinter login window with validation
feat(client): implement main chat window with background receiver thread
feat(client): add online users panel, private messaging, and history replay
feat(perf): add generate_graphs.py and sample performance_results.csv
docs: add README with Mininet and Wireshark testing instructions
docs: add full academic report (REPORT.md)
chore: add .gitignore and finalize submission package
```

---

## 10. Notes on Design Choices

Because no Assignment 5 source code was supplied for this submission, all
networking logic in `server.py` and `client_gui.py` was implemented from
scratch for Assignment 6, while keeping the wire protocol simple and
explicit (newline-delimited JSON) so it is easy to inspect in Wireshark's
"Follow TCP Stream" view and easy to extend. See `REPORT.md` §4 for a full
discussion of the components implemented and the design rationale.
