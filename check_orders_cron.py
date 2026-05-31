#!/usr/bin/env python3
"""Check orders.json for new orders and print alerts."""
import json, os

ORDERS_FILE = "/root/facebook-bot/orders.json"
STATE_FILE = "/root/facebook-bot/.last_order_state"

if not os.path.exists(ORDERS_FILE):
    exit(0)

with open(ORDERS_FILE) as f:
    current_orders = json.load(f)

if not current_orders:
    exit(0)

last_seen = ""
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        last_seen = f.read().strip()

newest_order_id = current_orders[-1]["id"]

if last_seen == newest_order_id:
    exit(0)

# Find new orders (orders after last_seen)
new_orders = []
for order in reversed(current_orders):
    if order["id"] == last_seen:
        break
    new_orders.append(order)

if not new_orders:
    exit(0)

# Save newest ID
with open(STATE_FILE, "w") as f:
    f.write(newest_order_id)

# Output alerts
for order in reversed(new_orders):
    c = order.get("customer", {})
    prod = order.get("product", "—")
    print(f"🛒 **নতুন অর্ডার!**")
    print(f"📋 অর্ডার ID: {order['id']}")
    print(f"👤 নাম: {c.get('name', '—')}")
    print(f"📞 ফোন: {c.get('phone', '—')}")
    print(f"📍 ঠিকানা: {c.get('address', '—')}")
    print(f"📦 পণ্য: {prod}")
    print(f"🕐 সময়: {order.get('created_at', '—')[:19]}")
    if order != new_orders[-1]:
        print()
