"""
metrics.py — QoS (Quality of Service) Tracker
Tracks latency, jitter, throughput, and packet loss in real time.
"""

import time
import statistics
import json
from collections import deque


class QoSTracker:
    """
    Records stats as packets arrive on the client side.

    Latency   = time from server send → client receive (uses server timestamp in header)
    Jitter    = variation between consecutive latency values
    Throughput = bytes received per second
    Loss      = packets that arrived out-of-sequence or not at all (detected via seq gaps)
    """

    def __init__(self, window_size=50):
        self._latencies = []          # (seq, latency_ms) for all packets
        self._recent_lat = deque(maxlen=window_size)   # rolling window
        self._recent_bytes = deque(maxlen=window_size) # (timestamp, bytes)
        self._missing = []            # sequence numbers that were skipped
        self._expected_seq = 0
        self._total_bytes = 0
        self._start = None

    def record_packet(self, seq, send_timestamp, data_len):
        """Call this each time a packet arrives."""
        now = time.time()
        if self._start is None:
            self._start = now

        # Latency
        latency_ms = (now - send_timestamp) * 1000.0
        self._latencies.append((seq, latency_ms))
        self._recent_lat.append(latency_ms)

        # Throughput
        self._total_bytes += data_len
        self._recent_bytes.append((now, data_len))

        # Detect missing packets via sequence number gaps
        if seq != self._expected_seq:
            for gap in range(self._expected_seq, seq):
                self._missing.append(gap)
        self._expected_seq = seq + 1

    # ── Live stats (rolling window) ──────────────────────────────────

    def live_latency_ms(self):
        return statistics.mean(self._recent_lat) if self._recent_lat else 0.0

    def live_jitter_ms(self):
        lats = list(self._recent_lat)
        if len(lats) < 2:
            return 0.0
        return statistics.mean(abs(lats[i] - lats[i-1]) for i in range(1, len(lats)))

    def live_throughput_kbps(self):
        now = time.time()
        recent = [(t, b) for t, b in self._recent_bytes if now - t <= 2.0]
        if not recent:
            return 0.0
        return sum(b for _, b in recent) * 8 / (2.0 * 1000)

    def live_loss_rate(self):
        total = len(self._latencies) + len(self._missing)
        return len(self._missing) / total if total else 0.0

    # ── Full summary at end of session ───────────────────────────────

    def summary(self):
        if not self._latencies:
            return {}
        lats = [l for _, l in self._latencies]
        duration = (time.time() - self._start) if self._start else 1
        jitters = [abs(lats[i] - lats[i-1]) for i in range(1, len(lats))]
        return {
            "packets_received": len(lats),
            "packets_missing": len(self._missing),
            "loss_rate_pct": self.live_loss_rate() * 100,
            "latency_ms": {
                "mean": statistics.mean(lats),
                "min": min(lats),
                "max": max(lats),
            },
            "jitter_ms": {
                "mean": statistics.mean(jitters) if jitters else 0.0,
                "max": max(jitters) if jitters else 0.0,
            },
            "throughput": {
                "total_bytes": self._total_bytes,
                "duration_sec": round(duration, 2),
                "avg_kbps": self._total_bytes * 8 / (duration * 1000),
            },
            "raw_latencies": lats,
            "raw_jitters": jitters,
        }

    def save_json(self, path="qos_results.json"):
        with open(path, "w") as f:
            json.dump(self.summary(), f, indent=2)
        print(f"[QoS] Saved → {path}")
