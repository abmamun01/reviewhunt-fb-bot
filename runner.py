#!/usr/bin/env python3
import os, sys, time

# Daemonize
pid = os.fork()
if pid > 0:
    # Parent writes PID and exits
    with open('/tmp/fbbot.pid', 'w') as f:
        f.write(str(pid))
    sys.exit(0)

# Child
os.setsid()
os.chdir('/root/facebook-bot')

# Read .env
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

sys.path.insert(0, '/root/facebook-bot')
from bot import app
import uvicorn

# Log
sys.stdout = open('/tmp/botlog.txt', 'w')
sys.stderr = sys.stdout

print(f'FB Bot starting (PID {os.getpid()})...', flush=True)
uvicorn.run(app, host='0.0.0.0', port=8644, log_level='info')
