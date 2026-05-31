#!/bin/bash
cd /root/facebook-bot
exec python3 -u run_bot.py > /tmp/bot_new.log 2>&1
