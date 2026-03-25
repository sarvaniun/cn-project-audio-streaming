"""
graphs.py — Generates QoS performance plots from qos_results.json

Plots:
  1. Latency per packet
  2. Jitter per packet
  3. Throughput over time
  4. Adaptive send rate (from server log)
  5. Multi-profile comparison bar chart

Run:  python graphs.py
  or: python graphs.py --compare qos_results_good.json qos_results_poor.json ...
"""

import json
import os
import glob
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ── Style ─────────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor": "#0f0f1a",
    "axes.facecolor": "#1a1a2e",
    "axes.edgecolor": "#444466",
    "axes.labelcolor": "#c8c8e8",
    "xtick.color": "#888aaa",
    "ytick.color": "#888aaa",
    "grid.color": "#2a2a4a",
    "grid.linestyle": "--",
    "text.color": "#e0e0f0",
    "font.family": "monospace",
    "lines.linewidth": 1.8,
})
C = ["#7ecfff", "#ff7eb3", "#7effa8", "#ffdd7e", "#bf7eff"]

# ── Args ──────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--json", default="qos_results.json")
parser.add_argument("--compare", nargs="*")
args = parser.parse_args()

if not os.path.exists(args.json):
    print(f"[graphs] {args.json} not found. Run client.py first.")
    exit(1)

with open(args.json) as f:
    data = json.load(f)

latencies = data.get("raw_latencies", [])
jitters   = data.get("raw_jitters", [])


# ── 1. Latency ────────────────────────────────────────────────────────
if latencies:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(latencies, color=C[0], alpha=0.8, label="Latency")
    # Rolling mean
    w = max(1, len(latencies) // 20)
    rolling = np.convolve(latencies, np.ones(w)/w, mode="valid")
    ax.plot(range(w-1, len(latencies)), rolling, color=C[1], linewidth=2, label=f"Rolling mean (w={w})")
    ax.axhline(np.mean(latencies), color="white", linestyle=":", alpha=0.5, label=f"Mean={np.mean(latencies):.1f}ms")
    ax.set(title="One-Way Latency per Packet", xlabel="Packet #", ylabel="Latency (ms)")
    ax.legend(framealpha=0.2)
    ax.grid(True)
    fig.tight_layout()
    fig.savefig("plot_latency.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("[graphs] Saved → plot_latency.png")

# ── 2. Jitter ─────────────────────────────────────────────────────────
if jitters:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.fill_between(range(len(jitters)), jitters, alpha=0.3, color=C[2])
    ax.plot(jitters, color=C[2], label="Jitter")
    ax.axhline(np.mean(jitters), color="white", linestyle=":", alpha=0.5, label=f"Mean={np.mean(jitters):.1f}ms")
    ax.set(title="Jitter (Inter-Packet Delay Variation)", xlabel="Packet #", ylabel="Jitter (ms)")
    ax.legend(framealpha=0.2)
    ax.grid(True)
    fig.tight_layout()
    fig.savefig("plot_jitter.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("[graphs] Saved → plot_jitter.png")

# ── 3. Throughput ─────────────────────────────────────────────────────
if latencies:
    avg_kbps = data.get("throughput", {}).get("avg_kbps", 0)
    # Approximate rolling throughput from latency timing
    times = np.cumsum([l / 1000.0 for l in latencies])
    chunk_bytes = 4096
    window = 2.0
    tput = []
    for i, t in enumerate(times):
        in_win = sum(chunk_bytes for tt in times if t - window <= tt <= t)
        tput.append(in_win * 8 / (window * 1000))

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(times, tput, color=C[3], label="Rolling throughput (2s)")
    ax.axhline(avg_kbps, color="white", linestyle=":", label=f"Avg={avg_kbps:.0f} kbps")
    ax.set(title="Estimated Throughput Over Time", xlabel="Time (s)", ylabel="Throughput (kbps)")
    ax.legend(framealpha=0.2)
    ax.grid(True)
    fig.tight_layout()
    fig.savefig("plot_throughput.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("[graphs] Saved → plot_throughput.png")

# ── 4. Adaptive rate (from server log) ────────────────────────────────
candidates = glob.glob("server_log_*.json")
if candidates:
    with open(candidates[0]) as f:
        sdata = json.load(f)
    history = sdata.get("adaptive_history", [])
    if history:
        t0 = history[0]["time"]
        times  = [h["time"] - t0 for h in history]
        sleeps = [h["sleep_ms"] for h in history]
        fills  = [h["buffer_fill"] * 100 for h in history]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
        ax1.plot(times, sleeps, color=C[4], label="Send interval (ms)")
        ax1.set(ylabel="Send Interval (ms)", title="Adaptive Rate Controller")
        ax1.legend(framealpha=0.2); ax1.grid(True)

        ax2.fill_between(times, fills, alpha=0.3, color=C[1])
        ax2.plot(times, fills, color=C[1], label="Buffer fill %")
        ax2.axhline(20, color="#ff7777", linestyle=":", alpha=0.7, label="Low (20%)")
        ax2.axhline(80, color="#77ff77", linestyle=":", alpha=0.7, label="High (80%)")
        ax2.set(ylabel="Buffer Fill (%)", xlabel="Time (s)", ylim=(0, 100))
        ax2.legend(framealpha=0.2); ax2.grid(True)

        fig.tight_layout()
        fig.savefig("plot_adaptive_rate.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("[graphs] Saved → plot_adaptive_rate.png")

# ── 5. Multi-profile comparison ───────────────────────────────────────
if args.compare:
    labels, mean_lats, mean_jits, losses = [], [], [], []
    for path in args.compare:
        if not os.path.exists(path):
            continue
        with open(path) as f:
            d = json.load(f)
        labels.append(os.path.basename(path).replace("qos_results_","").replace(".json",""))
        mean_lats.append(d.get("latency_ms", {}).get("mean", 0))
        mean_jits.append(d.get("jitter_ms", {}).get("mean", 0))
        losses.append(d.get("loss_rate_pct", 0))

    if labels:
        x = np.arange(len(labels))
        w = 0.25
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(x - w, mean_lats, w, label="Mean Latency (ms)", color=C[0], alpha=0.85)
        ax.bar(x,     mean_jits, w, label="Mean Jitter (ms)",  color=C[2], alpha=0.85)
        ax.bar(x + w, losses,    w, label="Loss Rate (%)",     color=C[1], alpha=0.85)
        ax.set(title="QoS Comparison Across Network Profiles", ylabel="Value")
        ax.set_xticks(x); ax.set_xticklabels(labels)
        ax.legend(framealpha=0.2); ax.grid(True, axis="y")
        fig.tight_layout()
        fig.savefig("plot_comparison.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("[graphs] Saved → plot_comparison.png")

print("\n[graphs] Done!")
