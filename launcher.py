#!/usr/bin/env python3
"""FB Bot launcher - reads keys from .env, starts uvicorn"""
import os, sys, pathlib

# Read keys from .env
env_path = pathlib.Path(__file__).parent / '.env'
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

print("🚀 FB Bot starting on port 8644...", flush=True)
uvicorn.run(app, host="0.0.0.0", port=8644, log_level="info")
