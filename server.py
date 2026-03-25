"""
server.py — Music Streaming Server
Streams song.wav to multiple clients over TCP with SSL/TLS encryption.

Person 2 additions on top of Person 1's base:
  - NetworkSimulator: wraps socket to inject artificial latency/jitter/loss
  - AdaptiveRateController: adjusts send rate based on client feedback
  - UDP feedback listener: receives buffer fill % from clients
  - SSL/TLS encryption
  - Saves per-client log to JSON

Run:  python server.py [--profile good|average|poor|terrible]
"""

import threading
import os
import time
import struct
import wave
import socket
import ssl
import json
import argparse

from network_sim import NetworkSimulator, PROFILES
from adaptive import AdaptiveRateController

# ── Config ────────────────────────────────────────────────────────────
SERVER_PORT   = 12000
FEEDBACK_PORT = 12001
CHUNK_SIZE    = 1024

# ── Arguments ─────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--profile", choices=list(PROFILES.keys()), default="average")
parser.add_argument("--loss",    type=float, default=None)
parser.add_argument("--latency", type=float, default=None)
parser.add_argument("--jitter",  type=float, default=None)
args = parser.parse_args()

sim_params = dict(PROFILES[args.profile])
if args.loss    is not None: sim_params["loss_rate"]  = args.loss
if args.latency is not None: sim_params["latency_ms"] = args.latency
if args.jitter  is not None: sim_params["jitter_ms"]  = args.jitter

print(f"[Server] Profile: {args.profile} → {sim_params}")

# ── Shared feedback store ─────────────────────────────────────────────
feedback = {}
feedback_lock = threading.Lock()

def feedback_receiver():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(('', FEEDBACK_PORT))
    udp.settimeout(1.0)
    print(f"[Server] UDP feedback listener on port {FEEDBACK_PORT}")
    while True:
        try:
            data, addr = udp.recvfrom(64)
            parts = data.decode().split(":")
            if len(parts) == 4 and parts[0] == "FILL":
                with feedback_lock:
                    feedback[addr[0]] = (float(parts[1]), float(parts[3]))
        except socket.timeout:
            continue
        except Exception:
            pass

# ── Per-client streaming thread ───────────────────────────────────────
def client_handler(conn, addr):
    ip = addr[0]
    print(f"[Server] Client connected: {ip}:{addr[1]}")

    sim = NetworkSimulator(conn, **sim_params, label=ip)
    arc = AdaptiveRateController()
    arc.start()

    try:
        wf = wave.open("song.wav", "rb")
    except FileNotFoundError:
        print("[Server] ERROR: song.wav not found!")
        conn.close()
        return

    seq = 0

    while True:
        chunk = wf.readframes(CHUNK_SIZE)
        if not chunk:
            break

        with feedback_lock:
            fill, loss = feedback.get(ip, (0.5, 0.0))
        arc.update_feedback(fill, loss)

        timestamp = time.time()
        header = struct.pack("!I d I", seq, timestamp, len(chunk))
        sim.send_packet(header + chunk, seq, timestamp)

        seq += 1
        time.sleep(arc.get_sleep())

    wf.close()
    arc.stop()

    stats = sim.get_stats()
    log = {
        "client": f"{ip}:{addr[1]}",
        "profile": args.profile,
        "stats": stats,
        "adaptive_history": arc.get_history(),
    }
    fname = f"server_log_{ip.replace('.','_')}_{addr[1]}.json"
    with open(fname, "w") as f:
        json.dump(log, f, indent=2)
    print(f"[Server] Done. Dropped {stats['total_dropped']}/{stats['total_sent']}. Log → {fname}")
    conn.close()

# ── Main ─────────────────────────────────────────────────────────────
threading.Thread(target=feedback_receiver, daemon=True).start()

# SSL context
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain("cert.pem", "key.pem")

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('', SERVER_PORT))
server.listen(10)
print(f"[Server] Listening on port {SERVER_PORT} (SSL enabled)...")

while True:
    conn, addr = server.accept()
    conn = context.wrap_socket(conn, server_side=True)
    filesize = os.path.getsize("song.wav")
    conn.sendall(str(filesize).encode())
    threading.Thread(target=client_handler, args=(conn, addr), daemon=True).start()