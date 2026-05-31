#!/usr/bin/env python3
"""Start FB Bot - runs uvicorn with proper env"""
import os, sys

# Real keys
os.environ["DEEPSEEK_API_KEY"] = "sk-8f034dbd2d9046a8b78548ad07bdeceb"
os.environ["VISION_API_KEY"] = "AIzaSyDGuBAs0XGyPwNt6FVGYNefkCQeLWRHwE"
os.environ["FB_PAGE_ACCESS_TOKEN"] = "EAATAcPO9Qd0BRiNu319DUayD4e0Xys5A99OG4ATCYvtaq3TlgxiQGPwyssPOwKZAw975EAI3ERmth1GOFADTxt2mP4I3TsSXhjOSaOToemyDY0J2C3AUb80JttDP22x7ZBZAM5XrRyYdox5ygOCDk3Q0ixEZCZByqKfln9NvN9bZB1KYD52LuoZB3pZAeHO49LrJd4eaqoGUjUeIXYT6cO5U2ZBI38QZDZD"
os.environ["FB_VERIFY_TOKEN"] = "hermes_bot_123"
os.environ["PORT"] = "8644"

import uvicorn
sys.path.insert(0, "/root/facebook-bot")

# Import the app
from bot import app

print("🚀 FB Bot starting...", flush=True)
uvicorn.run(app, host="0.0.0.0", port=8644, log_level="info")
