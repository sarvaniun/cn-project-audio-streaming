"""
client.py — Music Streaming Client
Receives audio from server and plays it back over SSL/TLS.

Person 2 additions:
  - QoSTracker: measures latency, jitter, throughput, packet loss
  - UDP feedback: sends buffer fill % back to server every 500ms
  - Live dashboard: prints QoS stats to terminal every 2 seconds
  - SSL/TLS encryption
  - Saves results to qos_results.json at end

Run:  python client.py [--host localhost] [--no-audio]
"""

import threading
import socket
import ssl
import struct
import time
import json
import argparse
from queue import Queue, Empty

from metrics import QoSTracker

# ── Config ────────────────────────────────────────────────────────────
HEADER_FORMAT = "!I d I"
HEADER_SIZE   = struct.calcsize(HEADER_FORMAT)
BUFFER_MAX    = 50
BUFFER_PRE    = 10

parser = argparse.ArgumentParser()
parser.add_argument("--host", default="localhost")
parser.add_argument("--port", type=int, default=12000)
parser.add_argument("--feedback-port", type=int, default=12001)
parser.add_argument("--no-audio", action="store_true")
args = parser.parse_args()

# ── Shared state ──────────────────────────────────────────────────────
buffer           = Queue(maxsize=BUFFER_MAX)
qos              = QoSTracker(window_size=60)
done_receiving   = threading.Event()
playback_started = threading.Event()


# ── Helper ────────────────────────────────────────────────────────────
def recv_exact(sock, size):
    data = b""
    while len(data) < size:
        pkt = sock.recv(size - len(data))
        if not pkt:
            return None
        data += pkt
    return data

def fill_ratio():
    return buffer.qsize() / BUFFER_MAX


# ── Thread 1: receive packets from server ─────────────────────────────
def get_audio(sock):
    received = 0
    try:
        filesize = int(sock.recv(1024).decode())
        print(f"[Client] File size: {filesize} bytes")
    except Exception as e:
        print(f"[Client] Failed to get filesize: {e}")
        done_receiving.set()
        return

    while received < filesize:
        header = recv_exact(sock, HEADER_SIZE)
        if not header:
            break
        seq, timestamp, length = struct.unpack(HEADER_FORMAT, header)
        chunk = recv_exact(sock, length)
        if not chunk:
            break
        received += len(chunk)
        qos.record_packet(seq, timestamp, len(chunk))
        buffer.put(chunk)

    done_receiving.set()
    print(f"[Client] Receive done. Total: {received} bytes")


# ── Thread 2: send buffer feedback to server ──────────────────────────
def send_feedback(host, port):
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while not done_receiving.is_set():
        msg = f"FILL:{fill_ratio():.4f}:LOSS:{qos.live_loss_rate():.4f}".encode()
        try:
            udp.sendto(msg, (host, port))
        except Exception:
            pass
        time.sleep(0.5)
    udp.close()


# ── Thread 3: play audio ──────────────────────────────────────────────
def play_audio():
    if args.no_audio:
        print("[Client] --no-audio: consuming buffer silently.")
        playback_started.set()
        while not (done_receiving.is_set() and buffer.empty()):
            try:
                buffer.get(timeout=0.5)
            except Empty:
                pass
        return

    try:
        import pyaudio
        import wave
        wf = wave.open("song.wav", "rb")
        p = pyaudio.PyAudio()
        stream = p.open(
            format=p.get_format_from_width(wf.getsampwidth()),
            channels=wf.getnchannels(),
            rate=wf.getframerate(),
            output=True,
            frames_per_buffer=4096
        )
        wf.close()
        print(f"[Client] Audio: {wf.getnchannels()}ch, {wf.getframerate()}Hz")
    except Exception as e:
        print(f"[Client] Audio init failed ({e}) — silent mode.")
        _silent_drain()
        return

    print(f"[Client] Buffering... ({BUFFER_PRE} chunks)")
    while buffer.qsize() < BUFFER_PRE:
        time.sleep(0.05)
    playback_started.set()
    print("[Client] Playback started.")

    while not (done_receiving.is_set() and buffer.empty()):
        try:
            stream.write(buffer.get(timeout=0.5))
        except Empty:
            print("[Client] Buffer underrun!")

    stream.stop_stream()
    stream.close()
    p.terminate()
    print("[Client] Playback done.")


def _silent_drain():
    while buffer.qsize() < BUFFER_PRE:
        time.sleep(0.05)
    playback_started.set()
    while not (done_receiving.is_set() and buffer.empty()):
        try:
            buffer.get(timeout=0.5)
        except Empty:
            pass


# ── Thread 4: live QoS dashboard ─────────────────────────────────────
def live_dashboard():
    playback_started.wait()
    print(f"\n{'Time':>6} | {'Latency':>10} | {'Jitter':>8} | {'Throughput':>12} | {'Loss':>6} | {'Buffer':>8}")
    print("-" * 70)
    start = time.time()
    while not done_receiving.is_set():
        print(f"{time.time()-start:>5.1f}s "
              f"| {qos.live_latency_ms():>8.1f}ms "
              f"| {qos.live_jitter_ms():>6.1f}ms "
              f"| {qos.live_throughput_kbps():>9.1f}kbps "
              f"| {qos.live_loss_rate()*100:>5.1f}% "
              f"| {fill_ratio()*100:>6.1f}%")
        time.sleep(2.0)


# ── Main ─────────────────────────────────────────────────────────────
context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock = context.wrap_socket(sock, server_hostname=args.host)
sock.connect((args.host, args.port))
print(f"[Client] Connected to {args.host}:{args.port} (SSL enabled)")

for t in [
    threading.Thread(target=get_audio,      args=(sock,),                         daemon=True),
    threading.Thread(target=send_feedback,   args=(args.host, args.feedback_port), daemon=True),
    threading.Thread(target=play_audio,                                            daemon=True),
    threading.Thread(target=live_dashboard,                                        daemon=True),
]:
    t.start()

done_receiving.wait()
time.sleep(2.0)

qos.save_json("qos_results.json")
s = qos.summary()
print("\n[QoS] Final Summary:")
print(f"  Packets received : {s.get('packets_received', 0)}")
print(f"  Packets missing  : {s.get('packets_missing', 0)}")
print(f"  Loss rate        : {s.get('loss_rate_pct', 0):.2f}%")
lat = s.get('latency_ms', {})
print(f"  Latency          : mean={lat.get('mean',0):.1f}ms  min={lat.get('min',0):.1f}ms  max={lat.get('max',0):.1f}ms")
jit = s.get('jitter_ms', {})
print(f"  Jitter           : mean={jit.get('mean',0):.1f}ms  max={jit.get('max',0):.1f}ms")
tp = s.get('throughput', {})
print(f"  Throughput       : {tp.get('avg_kbps',0):.1f} kbps")
print("\nRun  python graphs.py  to generate plots.")