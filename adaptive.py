"""
adaptive.py — Adaptive Rate Controller
Adjusts how fast the server sends chunks based on feedback from the client.

Simple AIMD logic (Additive Increase / Multiplicative Decrease):
  - If client buffer is low  → send faster (decrease sleep)
  - If client buffer is full → send slower (increase sleep)
  - If packet loss is high   → back off hard (increase sleep more)
  - Otherwise               → slowly speed up
"""

import threading
import time


class AdaptiveRateController:
    """Controls the time.sleep() between chunks on the server."""

    MIN_SLEEP = 0.005   # fastest: ~200 chunks/sec
    MAX_SLEEP = 0.08    # slowest: ~12 chunks/sec
    DEFAULT   = 0.02    # starting value (same as original server)
    STEP      = 0.001   # how much to adjust each tick

    def __init__(self):
        self._sleep = self.DEFAULT
        self._buffer_fill = 0.5   # 0.0 = empty, 1.0 = full
        self._loss_rate = 0.0
        self._lock = threading.Lock()
        self._running = False
        self.history = []   # log of adjustments

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False

    def update_feedback(self, buffer_fill, loss_rate):
        """Called when client sends back its buffer level and loss rate."""
        with self._lock:
            self._buffer_fill = buffer_fill
            self._loss_rate = loss_rate

    def get_sleep(self):
        with self._lock:
            return self._sleep

    def _loop(self):
        """Runs every 500ms and adjusts send rate."""
        while self._running:
            time.sleep(0.5)
            with self._lock:
                fill = self._buffer_fill
                loss = self._loss_rate
                reason = "stable"

                if loss > 0.10:
                    # High loss → slow down a lot
                    self._sleep = min(self.MAX_SLEEP, self._sleep + self.STEP * 5)
                    reason = f"high_loss({loss:.0%})"
                elif fill < 0.20:
                    # Buffer draining → send faster
                    self._sleep = max(self.MIN_SLEEP, self._sleep - self.STEP)
                    reason = f"low_buffer({fill:.0%})"
                elif fill > 0.80:
                    # Buffer nearly full → slow down
                    self._sleep = min(self.MAX_SLEEP, self._sleep + self.STEP * 2)
                    reason = f"high_buffer({fill:.0%})"
                elif loss < 0.02 and fill > 0.40:
                    # All good → slowly speed up
                    self._sleep = max(self.MIN_SLEEP, self._sleep - self.STEP * 0.5)
                    reason = "good"

                self.history.append({
                    "time": time.time(),
                    "sleep_ms": round(self._sleep * 1000, 2),
                    "buffer_fill": round(fill, 3),
                    "loss_rate": round(loss, 3),
                    "reason": reason,
                })

    def get_history(self):
        with self._lock:
            return list(self.history)
