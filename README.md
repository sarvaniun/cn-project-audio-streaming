#  Online Music Streaming Server

TCP socket-based music streaming with SSL/TLS, network simulation, adaptive rate control, and QoS metrics.

---

## Setup

```bash
pip install matplotlib pyaudio
```

Generate SSL certificate (one time):
```bash
"C:\Program Files\OpenSSL-Win64\bin\openssl.exe" req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"
```

---

## Run

Terminal 1:
```bash
python server.py --profile good
```

Terminal 2:
```bash
python client.py --host localhost
```

Profiles: `good`, `average`, `poor`, `terrible`

After streaming finishes:
```bash
python graphs.py
```

Or run everything at once:
```bash
python run_demo.py
```

---

## Files

| File | Description |
|------|-------------|
| `server.py` | Streams song.wav over TCP + SSL |
| `client.py` | Receives audio, plays it, tracks QoS |
| `network_sim.py` | Simulates delay, jitter, packet loss |
| `adaptive.py` | Adjusts send rate based on client buffer |
| `metrics.py` | Tracks latency, jitter, throughput, loss |
| `graphs.py` | Generates performance plots |
| `run_demo.py` | Runs all profiles, generates HTML report |

---
