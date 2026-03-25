"""
run_demo.py — Automated Demo Script
Runs all 4 network profiles back-to-back and generates a comparison report.

Usage:  python run_demo.py
"""

import subprocess
import sys
import os
import json
import time
import socket

PROFILES = ["good", "average", "poor", "terrible"]
PY = sys.executable

def wait_for_server(port=12000, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        try:
            socket.create_connection(("localhost", port), timeout=0.5).close()
            return True
        except OSError:
            time.sleep(0.2)
    return False

def run_profile(profile):
    print(f"\n{'='*50}\n  Profile: {profile.upper()}\n{'='*50}")

    srv = subprocess.Popen([PY, "server.py", "--profile", profile],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    if not wait_for_server():
        print(f"[demo] Server failed to start for {profile}")
        srv.terminate()
        return None

    cli = subprocess.Popen([PY, "client.py", "--no-audio"],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    try:
        cli.communicate(timeout=180)
    except subprocess.TimeoutExpired:
        cli.kill()

    srv.terminate()
    try:
        srv.wait(timeout=5)
    except subprocess.TimeoutExpired:
        srv.kill()

    result = f"qos_results_{profile}.json"
    if os.path.exists("qos_results.json"):
        os.replace("qos_results.json", result)
        print(f"[demo] Saved → {result}")
        return result
    return None

def make_report(results):
    rows = ""
    for profile, path in results.items():
        if not path or not os.path.exists(path):
            continue
        with open(path) as f:
            d = json.load(f)
        lat  = d.get("latency_ms", {})
        jit  = d.get("jitter_ms", {})
        tp   = d.get("throughput", {})
        loss = d.get("loss_rate_pct", 0)
        rows += f"""<tr>
          <td><b>{profile.upper()}</b></td>
          <td>{lat.get('mean',0):.1f}</td>
          <td>{jit.get('mean',0):.1f}</td>
          <td>{loss:.2f}%</td>
          <td>{tp.get('avg_kbps',0):.1f}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>QoS Demo Report</title>
<style>
  body{{font-family:monospace;background:#0f0f1a;color:#c8c8e8;padding:2rem}}
  h1{{color:#7ecfff}} h2{{color:#ff7eb3;margin-top:2rem}}
  table{{border-collapse:collapse;width:100%;margin-top:1rem}}
  th{{background:#1a1a2e;color:#7ecfff;padding:0.6rem 1rem;border:1px solid #333;text-align:left}}
  td{{padding:0.5rem 1rem;border:1px solid #2a2a4a}}
  .img-grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:1rem}}
  img{{width:100%;border:1px solid #333;border-radius:4px}}
</style></head>
<body>
<h1>🎵 QoS Demo Report — Music Streaming</h1>
<h2>📊 Metrics by Network Profile</h2>
<table>
  <tr><th>Profile</th><th>Latency Mean (ms)</th><th>Jitter Mean (ms)</th><th>Packet Loss</th><th>Throughput (kbps)</th></tr>
  {rows}
</table>
<h2>📈 Graphs</h2>
<div class="img-grid">
  <div><img src="plot_latency.png"><p>Latency per packet</p></div>
  <div><img src="plot_jitter.png"><p>Jitter</p></div>
  <div><img src="plot_throughput.png"><p>Throughput</p></div>
  <div><img src="plot_adaptive_rate.png"><p>Adaptive send rate</p></div>
</div>
<img src="plot_comparison.png" style="max-width:60%;margin-top:1rem">
</body></html>"""

    with open("demo_report.html", "w") as f:
        f.write(html)
    print("[demo] Report → demo_report.html")

# ── Main ─────────────────────────────────────────────────────────────
if not os.path.exists("song.wav"):
    print("[demo] ERROR: song.wav not found!")
    sys.exit(1)

results = {p: run_profile(p) for p in PROFILES}

compare = [v for v in results.values() if v and os.path.exists(v)]
if compare:
    subprocess.run([PY, "graphs.py", "--json", compare[0], "--compare"] + compare)

make_report(results)
print("\n[demo] Done! Open demo_report.html in your browser.")
