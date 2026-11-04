"""
FACE RECOGNITION BASED ATTENDANCE MONITORING SYSTEM
====================================================
One-click Ngrok Deployment Script
Run this file to start the server AND expose it online via ngrok.

Usage:
    python ngrok_run.py
    python ngrok_run.py --token YOUR_NGROK_TOKEN
"""

import sys
import os
import time
import argparse
import threading
import subprocess

# ─── Parse arguments ────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Start attendance system with ngrok tunnel")
parser.add_argument("--token", help="Your ngrok authtoken (from https://dashboard.ngrok.com/get-started/your-authtoken)")
parser.add_argument("--port", type=int, default=8000, help="Local port (default: 8000)")
args = parser.parse_args()

PORT = args.port

# ─── Setup ngrok authtoken if provided ──────────────────────────────────────
if args.token:
    from pyngrok import conf
    conf.get_default().auth_token = args.token
    print(f"[✔] Ngrok authtoken set.")

# ─── Check pyngrok is installed ─────────────────────────────────────────────
try:
    from pyngrok import ngrok, conf
except ImportError:
    print("[✖] pyngrok not installed. Run:  pip install pyngrok")
    sys.exit(1)

# ─── Start uvicorn in background thread ─────────────────────────────────────
print(f"\n{'='*60}")
print("  FACE RECOGNITION BASED ATTENDANCE MONITORING SYSTEM")
print(f"{'='*60}")
print(f"[→] Starting local server on port {PORT}...")

def run_uvicorn():
    os.system(f"uvicorn main:app --host 0.0.0.0 --port {PORT} --log-level warning")

server_thread = threading.Thread(target=run_uvicorn, daemon=True)
server_thread.start()

# Wait for server to come up
time.sleep(3)

# ─── Open ngrok tunnel ───────────────────────────────────────────────────────
print(f"[→] Opening ngrok tunnel...")
try:
    tunnel = ngrok.connect(PORT, "http")
    public_url = tunnel.public_url

    print(f"\n{'='*60}")
    print(f"  ✅  SYSTEM IS LIVE!")
    print(f"{'='*60}")
    print(f"")
    print(f"  🌐  Public URL (share this):  {public_url}")
    print(f"  🖥️   Local URL:               http://localhost:{PORT}")
    print(f"")
    print(f"  📌  Share the public URL with students/faculty")
    print(f"  🔐  Admin Login:  admin / admin@123")
    print(f"  📷  Webcam attendance works because it runs on THIS machine")
    print(f"")
    print(f"  Press Ctrl+C to stop the server")
    print(f"{'='*60}\n")

    # Keep alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[→] Shutting down...")
        ngrok.kill()
        print("[✔] Server stopped.")

except Exception as e:
    print(f"[✖] Ngrok error: {e}")
    print(f"")
    print(f"  → If you see 'authtoken' error:")
    print(f"    1. Sign up free at https://ngrok.com")
    print(f"    2. Get your token from https://dashboard.ngrok.com/get-started/your-authtoken")
    print(f"    3. Run:  python ngrok_run.py --token YOUR_TOKEN_HERE")
    print(f"")
    print(f"  → Your app still runs locally at:  http://localhost:{PORT}")
    print(f"")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
