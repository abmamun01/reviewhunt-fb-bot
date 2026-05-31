#!/usr/bin/env python3
import os, sys, time

# Fork
pid = os.fork()
if pid > 0:
    with open('/tmp/ngrok.pid', 'w') as f:
        f.write(str(pid))
    sys.exit(0)

# Child daemon - use subprocess to run ngrok
os.setsid()
os.chdir('/tmp')

import subprocess
with open('/tmp/ngrok.log', 'w') as log:
    subprocess.Popen(
        ['ngrok', 'http', '8644', '--url=unopened-mumps-strewn.ngrok-free.dev', '--log=stdout'],
        stdout=log, stderr=subprocess.STDOUT
    )
