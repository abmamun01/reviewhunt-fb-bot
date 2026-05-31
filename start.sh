#!/bin/bash
set -a
. /root/facebook-bot/.env
set +a
cd /root/facebook-bot && exec python3 run_bot.py
