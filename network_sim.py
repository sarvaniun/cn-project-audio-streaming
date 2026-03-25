"""
network_sim.py — Simulates real network conditions
Adds artificial delay, jitter, and packet drops to the socket.
"""

import time
import random
import struct

HEADER_FORMAT = "!I d I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

PROFILES = {
    "good":     {"latency_ms": 1,  "jitter_ms": 1,  "loss_rate": 0.0},
    "average":  {"latency_ms": 5,  "jitter_ms": 2,  "loss_rate": 0.0},
    "poor":     {"latency_ms": 10, "jitter_ms": 5,  "loss_rate": 0.0},
    "terrible": {"latency_ms": 20, "jitter_ms": 10, "loss_rate": 0.0},
}


class NetworkSimulator:
    def __init__(self, sock, latency_ms=50, jitter_ms=20, loss_rate=0.05, label="client"):
        self.sock = sock
        self.latency_ms = latency_ms
        self.jitter_ms = jitter_ms
        self.loss_rate = loss_rate
        self.label = label
        self.sent = 0
        self.dropped = 0
        self.packet_log = []

    def send_packet(self, pkt, seq, timestamp):
        """Send one packet — may drop it or delay it."""
        self.sent += 1
        dropped = random.random() < self.loss_rate

        delay_ms = self.latency_ms + random.uniform(-self.jitter_ms, self.jitter_ms)
        delay_ms = max(0, delay_ms)

        self.packet_log.append({"seq": seq, "delay_ms": round(delay_ms, 2), "dropped": dropped})

        if dropped:
            self.dropped += 1
            return False

        time.sleep(delay_ms / 1000.0)
        try:
            self.sock.sendall(pkt)
        except Exception:
            pass
        return True

    def get_stats(self):
        return {
            "total_sent": self.sent,
            "total_dropped": self.dropped,
            "effective_loss_rate": self.dropped / self.sent if self.sent else 0.0,
        }
