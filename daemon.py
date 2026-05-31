#!/usr/bin/env python3
"""FB Bot - forks into background"""
import os, sys, pathlib, time

# Daemonize - fork to background
pid = os.fork()
if pid > 0:
    # Parent exits
    sys.exit(0)

# Child continues (daemon)
os.setsid()
os.chdir("/root/facebook-bot")

# Read .env
env_path = pathlib.Path(".") / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip()

sys.path.insert(0, str(env_path.parent))
from bot import app
import uvicorn

# Log to file
sys.stdout = open("/tmp/fbbot.log", "w")
sys.stderr = sys.stdout

print(f"🚀 FB Bot starting on port 8644 (PID {os.getpid()})...", flush=True)
uvicorn.run(app, host="0.0.0.0", port=8644, log_level="info")
