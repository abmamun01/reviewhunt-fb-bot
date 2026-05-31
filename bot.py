"""
Facebook Messenger Bot - AI Customer Support
Powered by DeepSeek API + Vision API
Always replies in Bangla
"""

import os
import json
import hashlib
import hmac
import logging
import re
from typing import Optional
from datetime import datetime

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse

# ─── Configuration ───────────────────────────────────────────────────────

CONFIG = {
    # Facebook
    "FB_VERIFY_TOKEN": os.getenv("FB_VERIFY_TOKEN", "hermes_bot_123"),
    "FB_PAGE_ACCESS_TOKEN": os.getenv("FB_PAGE_ACCESS_TOKEN", "YOUR_FB_PAGE_TOKEN"),

    # DeepSeek
    "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY", "YOUR_DEEPSEEK_API_KEY"),
    "DEEPSEEK_API_URL": "https://api.deepseek.com/v1/chat/completions",

    # Delivery Info
    "DELIVERY_CHARGE_DHAKA": 60,
    "DELIVERY_CHARGE_OUTSIDE": 120,
    "DELIVERY_TIME_DHAKA": "১ দিন (1 day)",
    "DELIVERY_TIME_OUTSIDE": "২-৩ দিন (2-3 days)",

    # Vision API (Gemini - free tier)
    "VISION_API_KEY": os.getenv("VISION_API_KEY", "YOUR_GEMINI_API_KEY"),
    "VISION_API_URL": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",

    # Bot
    "PORT": int(os.getenv("PORT", "8644")),
    "HOST": os.getenv("HOST", "0.0.0.0"),
    "PUBLIC_URL": os.getenv("PUBLIC_URL", "https://unopened-mumps-strewn.ngrok-free.dev"),
}

# ─── File Paths ────────────────────────────────────────────────────────────

PRODUCTS_FILE = os.path.join(os.path.dirname(__file__), "products.json")
ORDERS_FILE = os.path.join(os.path.dirname(__file__), "orders.json")

# ─── Product Knowledge Base ──────────────────────────────────────────────

PRODUCTS_FILE = os.path.join(os.path.dirname(__file__), "products.json")

class ProductDB:
    def __init__(self):
        self.products = []
        self.upcoming = []
        self.load()

    def load(self):
        if os.path.exists(PRODUCTS_FILE):
            with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.products = data.get("products", [])
                self.upcoming = data.get("upcoming", [])
        logging.info(f"Loaded {len(self.products)} products, {len(self.upcoming)} upcoming")

    def get_context(self) -> str:
        """Format products into a context string for the AI"""
        lines = ["📦 **পণ্যের তালিকা (Product Catalog):**\n"]

        for p in self.products:
            price_str = f"{p.get('price', 0)} টাকা" if p.get('price', 0) > 0 else "দাম জানতে চাইলে জিজ্ঞাসা করুন"
            lines.append(f"- {p.get('name_bn', p['name'])} | দাম: {price_str} | বিভাগ: {p.get('category', 'N/A')}")
            if p.get('description_bn'):
                lines.append(f"  বিবরণ: {p['description_bn']}")
            if p.get('in_stock'):
                lines.append(f"  ✅ স্টকে আছে")
            else:
                lines.append(f"  ❌ স্টকে নেই")
            if p.get('variants'):
                lines.append(f"  ভেরিয়েন্ট: {', '.join(p['variants'])}")

        if self.upcoming:
            lines.append("\n🔜 **আগামী পণ্য (Upcoming):**\n")
            for u in self.upcoming:
                lines.append(f"- {u.get('name_bn', u['name'])} — {u.get('eta', 'শীঘ্রই')}")
                if u.get('description_bn'):
                    lines.append(f"  {u['description_bn']}")

        return "\n".join(lines)


# ─── Order Database ─────────────────────────────────────────────────────

class OrderDB:
    def __init__(self):
        self.orders = []
        self.load()

    def load(self):
        if os.path.exists(ORDERS_FILE):
            try:
                with open(ORDERS_FILE, "r", encoding="utf-8") as f:
                    self.orders = json.load(f)
            except:
                self.orders = []
        logging.info(f"📋 Loaded {len(self.orders)} orders")

    def save(self):
        os.makedirs(os.path.dirname(ORDERS_FILE) or ".", exist_ok=True)
        with open(ORDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.orders, f, ensure_ascii=False, indent=2)
        logging.info(f"💾 Saved {len(self.orders)} orders")

    def add_order(self, name, phone, address, product, sender_id):
        order = {
            "id": f"ORD-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{len(self.orders)+1:03d}",
            "customer": {"name": name, "phone": phone, "address": address},
            "product": product,
            "sender_id": sender_id,
            "status": "pending",
            "created_at": datetime.now().isoformat()
        }
        self.orders.append(order)
        self.save()
        return order

    def get_orders(self, limit=50):
        return list(reversed(self.orders))[:limit]


def extract_order_info(full_conversation: str) -> dict:
    """Use DeepSeek to extract order info from Bangla conversation"""
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": (
                "You are an order data extractor. Extract customer order info from Bangla conversation.\n"
                "Return ONLY valid JSON with fields: name, phone, address, product\n"
                "If any field is missing, set it to null (not empty string).\n"
                "Example: {\"name\": \"Rahim\", \"phone\": \"01712345678\", \"address\": \"Dhaka\", \"product\": \"Knee Brace\"}\n"
                "If order info is incomplete, return: {\"name\": null, \"phone\": null, \"address\": null, \"product\": null}"
            )},
            {"role": "user", "content": f"Extract order info from this conversation:\n{full_conversation[:2000]}"}
        ],
        "temperature": 0.1,
        "max_tokens": 200
    }

    headers = {
        "Authorization": f"Bearer {CONFIG['DEEPSEEK_API_KEY']}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(CONFIG["DEEPSEEK_API_URL"], headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        # Extract JSON from response (it might be wrapped in ```json ... ```)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data = json.loads(text)
        if data.get("name") and data.get("phone") and data.get("address"):
            return data
        return None
    except Exception as e:
        logging.warning(f"Order extraction failed: {e}")
        return None


def is_order_confirmed(bot_reply: str) -> bool:
    """Detect if bot reply confirms an order"""
    confirm_keywords = ["✅", "কনফার্ম", "কনফর্ম", "অর্ডার কনফার্ম",
                        "অর্ডার কনফর্ম", "অর্ডার নিশ্চিত", "ধন্যবাদ",
                        "আপনার অর্ডার", "অর্ডারটি কনফার্ম"]
    return any(kw in bot_reply for kw in confirm_keywords)


# ─── DeepSeek API ────────────────────────────────────────────────────────

def ask_deepseek(user_message: str, system_context: str, is_order_flow: bool = False, history: list = None) -> str:
    """Send a message to DeepSeek with conversation history, get a response in Bangla"""
    if is_order_flow:
        system_msg = (
            "তুমি FB Bot - একটি পেশাদার সেলস ম্যানেজার। "
            "তুমি শুধুমাত্র বাংলায় উত্তর দেবে। "
            "তোমার উত্তর হবে সংক্ষিপ্ত, ভদ্র এবং পেশাদার। "
            "গ্রাহক অর্ডার কনফার্ম করতে চাইলে শুধুমাত্র এই ৩টি তথ্য নাও:\n"
            "1️⃣ নাম\n"
            "2️⃣ মোবাইল নম্বর\n"
            "3️⃣ ঠিকানা (সম্পূর্ণ)\n\n"
            "অতিরিক্ত কোনো তথ্য চাইবে না। তথ্য নেওয়ার পর বলো:\n"
            "'✅ আপনার অর্ডার কনফার্ম করা হয়েছে! ধন্যবাদ।'\n\n"
            "📦 **ডেলিভারি চার্জ:**\n"
            "• ঢাকার ভিতরে: ৬০ টাকা — ডেলিভারি সময়: ১ দিন\n"
            "• ঢাকার বাইরে: ১২০ টাকা — ডেলিভারি সময়: ২-৩ দিন\n\n"
            "পণ্য সম্পর্কে প্রশ্ন করলে সংক্ষিপ্ত ও পেশাদার উত্তর দাও।\n\n"
            f"পণ্যের তালিকা:\n{system_context}"
        )
    else:
        system_msg = (
            "তুমি FB Bot - একটি পেশাদার সেলস ম্যানেজার। "
            "তুমি শুধুমাত্র বাংলায় উত্তর দেবে। "
            "তোমার উত্তর সংক্ষিপ্ত, ভদ্র এবং পেশাদার হবে। "
            "পণ্য সম্পর্কে তথ্য দাও, দাম বলো এবং গ্রাহক অর্ডার দিতে চাইলে "
            "শুধু নাম, মোবাইল নম্বর ও ঠিকানা চাও। "
            "অপ্রয়োজনীয় কথা বলবে না।\n\n"
            "📦 **ডেলিভারি চার্জ:**\n"
            "• ঢাকার ভিতরে: ৬০ টাকা — ডেলিভারি সময়: ১ দিন\n"
            "• ঢাকার বাইরে: ১২০ টাকা — ডেলিভারি সময়: ২-৩ দিন\n\n"
            f"পণ্যের তালিকা:\n{system_context}"
        )

    # Build messages array with history
    messages = [{"role": "system", "content": system_msg}]
    if history:
        messages.extend(history[-10:])  # Last 5 exchanges max
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.5,
        "max_tokens": 300,
        "stream": False
    }

    headers = {
        "Authorization": f"Bearer {CONFIG['DEEPSEEK_API_KEY']}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(
            CONFIG["DEEPSEEK_API_URL"],
            headers=headers,
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.error(f"DeepSeek API error: {e}")
        return "দুঃখিত, আমি এখন উত্তর দিতে পারছি না। অনুগ্রহ করে কিছুক্ষণ পর আবার চেষ্টা করুন। 🙏"


# ─── DeepSeek API ────────────────────────────────────────────────────────




def ask_ai(user_message: str, system_context: str, history: list = None) -> str:
    """Ask DeepSeek for a response"""
    return ask_deepseek(user_message, system_context, history=history)


# ─── Vision API (Gemini - for image recognition) ─────────────────────────

def analyze_image(image_url: str) -> str:
    """Send an image URL to Gemini Vision API and get a description"""
    if CONFIG["VISION_API_KEY"] == "YOUR_GEMINI_API_KEY":
        return "ছবি বিশ্লেষণ কনফিগার করা হয়নি।"

    url = f"{CONFIG['VISION_API_URL']}?key={CONFIG['VISION_API_KEY']}"

    payload = {
        "contents": [{
            "parts": [
                {"text": "এই ছবিতে কি পণ্য আছে? বিস্তারিত বর্ণনা দাও বাংলায়। যদি কোনো পণ্য চিনতে পারো, তার নাম ও বৈশিষ্ট্য বলো।"},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": None  # Will be fetched below
                    }
                }
            ]
        }]
    }

    try:
        # Download the image from Facebook
        img_resp = requests.get(image_url, timeout=15)
        img_resp.raise_for_status()

        import base64
        img_b64 = base64.b64encode(img_resp.content).decode("utf-8")

        # Guess mime type from URL
        mime = "image/jpeg"
        if ".png" in image_url.lower():
            mime = "image/png"
        elif ".gif" in image_url.lower():
            mime = "image/gif"
        elif ".webp" in image_url.lower():
            mime = "image/webp"

        payload["contents"][0]["parts"][1]["inline_data"] = {
            "mime_type": mime,
            "data": img_b64
        }

        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    except Exception as e:
        logging.error(f"Vision API error: {e}")
        return "ছবি বিশ্লেষণ করতে সমস্যা হয়েছে। অনুগ্রহ করে পণ্যের নাম লিখে জানান।"


# ─── Facebook Messenger API ──────────────────────────────────────────────

def send_message(recipient_id: str, text: str):
    """Send a message to a Facebook user"""
    url = f"https://graph.facebook.com/v21.0/me/messages"
    params = {"access_token": CONFIG["FB_PAGE_ACCESS_TOKEN"]}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }

    try:
        resp = requests.post(url, params=params, json=payload, timeout=15)
        resp.raise_for_status()
        logging.info(f"Sent message to {recipient_id}")
        return resp.json()
    except Exception as e:
        logging.error(f"Facebook API error: {e}")
        return None


def send_typing(recipient_id: str, action: str = "typing_on"):
    """Show typing indicator"""
    url = f"https://graph.facebook.com/v21.0/me/messages"
    params = {"access_token": CONFIG["FB_PAGE_ACCESS_TOKEN"]}
    payload = {
        "recipient": {"id": recipient_id},
        "sender_action": action
    }
    try:
        requests.post(url, params=params, json=payload, timeout=10)
    except:
        pass


# ─── FastAPI Server ──────────────────────────────────────────────────────

app = FastAPI(title="Auto Reply FB Messenger")
product_db = ProductDB()
order_db = OrderDB()

# In-memory conversation store (last 20 msgs per sender)
conversations = {}


def track_conversation(sender_id: str, user_text: str, bot_reply: str):
    """Keep recent conversation history for order extraction and context"""
    if sender_id not in conversations:
        conversations[sender_id] = []
    conversations[sender_id].append({"role": "user", "content": user_text})
    conversations[sender_id].append({"role": "assistant", "content": bot_reply})
    # Keep last 10 exchanges (20 messages)
    conversations[sender_id] = conversations[sender_id][-20:]


@app.get("/api/status")
async def api_status():
    """JSON status endpoint for the dashboard"""
    return {
        "status": "alive",
        "bot": "FB Bot",
        "language": "Bangla (বাংলা)",
        "ai": "DeepSeek + Gemini Vision",
        "products": len(product_db.products),
        "upcoming": len(product_db.upcoming),
        "webhook_url": f"{CONFIG['PUBLIC_URL']}/webhook/ffbautoreply",
        "facebook_connected": CONFIG["FB_PAGE_ACCESS_TOKEN"] != "YOUR_FB_PAGE_TOKEN",
        "deepseek_ready": CONFIG["DEEPSEEK_API_KEY"] != "YOUR_DEEPSEEK_API_KEY",
        "vision_ready": CONFIG["VISION_API_KEY"] != "YOUR_GEMINI_API_KEY",
        "delivery": {
            "inside_dhaka": {"charge": CONFIG["DELIVERY_CHARGE_DHAKA"], "time": CONFIG["DELIVERY_TIME_DHAKA"]},
            "outside_dhaka": {"charge": CONFIG["DELIVERY_CHARGE_OUTSIDE"], "time": CONFIG["DELIVERY_TIME_OUTSIDE"]}
        }
    }


@app.get("/")
async def root():
    """Admin Dashboard - Auto Reply FB Messenger"""
    html = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FB Bot - Auto Reply Messenger</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
body{background:#0f0f1a;color:#e0e0e0;min-height:100vh;display:flex;flex-direction:column}
.topbar{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:20px 30px;border-bottom:1px solid #2a2a4a;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}
.topbar h1{font-size:22px;font-weight:600;display:flex;align-items:center;gap:10px}
.topbar h1 span{background:#5865f2;font-size:11px;padding:3px 10px;border-radius:20px;color:#fff;font-weight:500}
.status-dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}
.green{background:#43b581;box-shadow:0 0 8px #43b58180}
.red{background:#f04747;box-shadow:0 0 8px #f0474780}
.container{max-width:1100px;margin:0 auto;padding:30px 20px;width:100%}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:30px}
.stat-card{background:#1a1a2e;border:1px solid #2a2a4a;border-radius:12px;padding:20px;transition:transform 0.2s}
.stat-card:hover{transform:translateY(-2px);border-color:#5865f2}
.stat-card .label{font-size:12px;color:#8e8ea0;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.stat-card .value{font-size:28px;font-weight:700;color:#fff}
.stat-card .sub{font-size:13px;color:#6b6b80;margin-top:4px}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:30px}
@media(max-width:700px){.two-col{grid-template-columns:1fr}}
.section{background:#1a1a2e;border:1px solid #2a2a4a;border-radius:12px;padding:20px}
.section h2{font-size:15px;font-weight:600;margin-bottom:16px;color:#b5b5c8;text-transform:uppercase;letter-spacing:1px}
.section h2 i{margin-right:8px}
.conn-row{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #252540}
.conn-row:last-child{border-bottom:none}
.conn-name{font-size:14px;color:#c0c0d0}
.conn-status{font-size:13px}
.badge{padding:4px 12px;border-radius:20px;font-size:11px;font-weight:600}
.badge-ok{background:#43b58120;color:#43b581;border:1px solid #43b58140}
.badge-warn{background:#f0a02020;color:#f0a020;border:1px solid #f0a02040}
.badge-off{background:#f0474720;color:#f04747;border:1px solid #f0474740}
.product-item{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #252540;font-size:14px}
.product-item:last-child{border-bottom:none}
.prod-name{color:#e0e0e0}
.prod-price{color:#43b581;font-weight:500}
.prod-stock{font-size:12px}
.footer{text-align:center;padding:20px;color:#4a4a60;font-size:12px;margin-top:auto}
.url-box{background:#252540;border-radius:8px;padding:10px 14px;font-family:monospace;font-size:13px;color:#8e8ea0;word-break:break-all;margin-top:10px;display:flex;justify-content:space-between;align-items:center;gap:10px}
.url-box button{background:#5865f2;border:none;color:#fff;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:12px;white-space:nowrap}
.url-box button:hover{background:#4752c4}
.tooltip{font-size:12px;color:#43b581;opacity:0;transition:opacity 0.3s}
.tooltip.show{opacity:1}
</style>
</head>
<body>
<div class="topbar">
<div>
<h1>🤖 FB Bot <span>v1.0</span></h1>
<div style="font-size:13px;color:#6b6b80;margin-top:4px">Professional sales manager — short, polite, Bangla 🇧🇩</div>
</div>
<div style="display:flex;align-items:center;gap:15px;font-size:13px">
<span id="liveStatus"><span class="status-dot green"></span> Online</span>
<a href="https://developers.facebook.com/apps" target="_blank" style="color:#5865f2;text-decoration:none">Meta Console →</a>
</div>
</div>
<div class="container" id="app">
<div class="stats-grid">
<div class="stat-card">
<div class="label">📦 Products</div>
<div class="value" id="prodCount">—</div>
<div class="sub" id="prodSub">In your catalog</div>
</div>
<div class="stat-card">
<div class="label">🧠 AI Engine</div>
<div class="value" style="font-size:18px" id="aiEngine">—</div>
<div class="sub">DeepSeek + Gemini Vision</div>
</div>
<div class="stat-card">
<div class="label">🔌 Webhook</div>
<div class="value" style="font-size:17px" id="webhookStatus">—</div>
<div class="sub" id="webhookSub">Facebook callback</div>
</div>
<div class="stat-card">
    <div class="label">🌐 Public URL</div>
    <div class="value" style="font-size:16px">ngrok ✅</div>
    <div class="sub">Active tunnel</div>
</div>
<div class="stat-card">
    <div class="label">📦 Delivery</div>
    <div class="value" style="font-size:16px">Dhaka ৬০৳</div>
    <div class="sub">Outside ১২০৳ — ২-৩ days</div>
</div>
<div class="stat-card">
    <div class="label">📋 Orders</div>
    <div class="value" id="orderCount">0</div>
    <div class="sub" id="orderSub">Total placed</div>
</div>
</div>
<div class="two-col">
<div class="section">
<h2><i>🔌</i> Connection Status</h2>
<div>
<div class="conn-row">
<span class="conn-name">🧠 AI Engine</span>
<span class="conn-status"><span id="aiBadge" class="badge badge-ok">✅ Connected</span></span>
</div>
<div class="conn-row">
<span class="conn-name">👁️ Gemini Vision</span>
<span class="conn-status"><span id="visionBadge" class="badge badge-ok">✅ Connected</span></span>
</div>
<div class="conn-row">
<span class="conn-name">📘 Facebook Page</span>
<span class="conn-status"><span id="fbBadge" class="badge badge-ok">✅ Connected</span></span>
</div>
<div class="conn-row">
<span class="conn-name">🌐 ngrok Tunnel</span>
<span class="conn-status"><span class="badge badge-ok">✅ Active</span></span>
</div>
</div>
<div class="url-box">
<span>__PUBLIC_URL__/webhook/ffbautoreply</span>
<button onclick="copyUrl()">📋 Copy</button>
</div>
<div id="copyTooltip" class="tooltip">Copied!</div>
</div>
<div class="section">
<h2><i>📋</i> Quick Actions</h2>
<div class="conn-row">
<span class="conn-name">🔄 Reload Products</span>
<button onclick="reloadProducts()" style="background:#43b581;border:none;color:#fff;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:12px">Reload</button>
</div>
<div class="conn-row">
<span class="conn-name">🛒 Open Meta Developer Console</span>
<a href="https://developers.facebook.com/apps" target="_blank" style="background:#5865f2;border:none;color:#fff;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:12px;text-decoration:none">Open →</a>
</div>
<div class="conn-row">
<span class="conn-name">📄 View Products (JSON)</span>
<a href="/api/products" target="_blank" style="background:#2a2a4a;border:1px solid #3a3a5a;color:#fff;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:12px;text-decoration:none">View</a>
</div>
<div class="conn-row">
<span class="conn-name">🗄️ Server Config</span>
<span style="font-family:monospace;font-size:12px;color:#6b6b80">Port 8644</span>
</div>
</div>
</div>
<div class="section">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
<h2 style="margin:0"><i>📦</i> Products in Catalog</h2>
<span style="font-size:12px;color:#6b6b80" id="productCountLabel">Loading...</span>
</div>
<div id="productList">
<div style="color:#6b6b80;font-size:14px;text-align:center;padding:20px">Loading products...</div>
</div>
</div>

<div class="section" style="margin-top:16px">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
<h2 style="margin:0"><i>📋</i> Recent Orders</h2>
<span style="font-size:12px;color:#6b6b80" id="orderCountLabel">Loading...</span>
</div>
<div id="orderList">
<div style="color:#6b6b80;font-size:14px;text-align:center;padding:20px">No orders yet</div>
</div>
</div>

</div>
<div class="footer">
FB Bot — Professional Sales Manager — Made for Max's Store 🚀
</div>
<script>
async function loadStatus(){try{let r=await fetch('/api/status'),d=await r.json();document.getElementById('prodCount').textContent=d.products;document.getElementById('prodSub').textContent=d.products+' products in catalog';document.getElementById('aiEngine').textContent='DeepSeek 🤖';document.getElementById('webhookStatus').textContent=d.facebook_connected?'✅ Active':'⚠️ Not Set';document.getElementById('webhookSub').textContent=d.facebook_connected?'Facebook connected':'Configure in Meta Console';let lt=document.getElementById('liveStatus');lt.innerHTML=d.status==='alive'?'<span class="status-dot green"></span> Online':'<span class="status-dot red"></span> Offline'}catch(e){document.getElementById('liveStatus').innerHTML='<span class="status-dot red"></span> Offline'}}
async function loadProducts(){try{let r=await fetch('/api/products'),d=await r.json();let list=document.getElementById('productList');let label=document.getElementById('productCountLabel');let p=d.products||[];label.textContent=p.length+' products';if(p.length===0){list.innerHTML='<div style="color:#6b6b80;font-size:14px;text-align:center;padding:20px">No products loaded yet</div>';return}list.innerHTML='';p.forEach(pr=>{let div=document.createElement('div');div.className='product-item';let price=pr.price>0?'৳ '+pr.price:'—';let stock=pr.in_stock?'✅ In Stock':'❌ Out of Stock';let name=pr.name_bn||pr.name;div.innerHTML='<div><div class="prod-name">'+name+'</div><div style="font-size:11px;color:#6b6b80;margin-top:2px">'+pr.category+'</div></div><div style="text-align:right"><div class="prod-price">'+price+'</div><div class="prod-stock" style="color:'+(pr.in_stock?'#43b581':'#f04747')+'">'+stock+'</div></div>';list.appendChild(div)})}catch(e){document.getElementById('productList').innerHTML='<div style="color:#f04747;font-size:14px;text-align:center;padding:20px">Failed to load products</div>'}}
async function reloadProducts(){try{let b=document.querySelector('[onclick="reloadProducts()"]');b.textContent='⏳...';b.disabled=true;let r=await fetch('/reload-products',{method:'POST'});if(!r.ok)throw Error();await loadProducts();await loadStatus();b.textContent='✅ Done!';setTimeout(()=>{b.textContent='Reload';b.disabled=false},1500)}catch(e){b.textContent='Reload';b.disabled=false;alert('Reload failed')}}
function copyUrl(){navigator.clipboard.writeText('__PUBLIC_URL__/webhook/ffbautoreply');let t=document.getElementById('copyTooltip');t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2000)}
async function loadOrders(){try{let r=await fetch('/api/orders'),d=await r.json();let list=document.getElementById('orderList');let label=document.getElementById('orderCountLabel');let oc=document.getElementById('orderCount');let os=document.getElementById('orderSub');let o=d.orders||[];oc.textContent=o.length;os.textContent=o.length+' total';label.textContent=o.length+' orders';if(o.length===0){list.innerHTML='<div style="color:#6b6b80;font-size:14px;text-align:center;padding:20px">No orders yet</div>';return}let html='<div style="display:grid;grid-template-columns:auto 1fr auto;gap:8px;padding:8px 0;border-bottom:1px solid #252540;font-size:11px;color:#6b6b80;font-weight:600"><span>ORDER ID</span><span>CUSTOMER</span><span>PRODUCT</span></div>';o.forEach(ord=>{let c=ord.customer||{};html+='<div style="display:grid;grid-template-columns:auto 1fr auto;gap:8px;padding:8px 0;border-bottom:1px solid #252540;font-size:13px"><span style="color:#5865f2;font-family:monospace;font-size:11px">'+ord.id+'</span><span><strong>'+(c.name||'?')+'</strong><br><span style="font-size:11px;color:#8e8ea0">'+(c.phone||'')+' | '+(c.address||'')+'</span></span><span class="badge badge-ok" style="font-size:10px">'+(ord.product||'—')+'</span></div>'});list.innerHTML=html}
loadStatus();loadProducts();loadOrders();setInterval(loadStatus,10000);setInterval(loadOrders,15000);
</script>
</body>
</html>"""
    return HTMLResponse(content=html.replace("__PUBLIC_URL__", CONFIG["PUBLIC_URL"]))


@app.get("/api/products")
async def api_products():
    """JSON product catalog for the dashboard"""
    data = {"products": [], "upcoming": []}
    for p in product_db.products:
        data["products"].append({
            "name": p.get("name", ""),
            "name_bn": p.get("name_bn", ""),
            "category": p.get("category", ""),
            "price": p.get("price", 0),
            "in_stock": p.get("in_stock", False)
        })
    for u in product_db.upcoming:
        data["upcoming"].append({
            "name": u.get("name", ""),
            "name_bn": u.get("name_bn", ""),
            "eta": u.get("eta", "")
        })
    return data


@app.get("/api/orders")
async def api_orders():
    """JSON order list for the dashboard"""
    return {"orders": order_db.get_orders(50)}


@app.post("/reload-products")
async def reload_products():
    """Reload products from products.json without restart"""
    product_db.load()
    return {
        "status": "ok",
        "products": len(product_db.products),
        "upcoming": len(product_db.upcoming)
    }


@app.get("/webhook")
@app.get("/webhook/ffbautoreply")
async def verify_webhook(request: Request):
    """Facebook verification webhook (uses hub.mode, hub.verify_token, hub.challenge)"""
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token == CONFIG["FB_VERIFY_TOKEN"]:
        return int(challenge) if challenge else 200
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
@app.post("/webhook/ffbautoreply")
async def handle_webhook(request: Request):
    """Receive messages from Facebook"""
    body = await request.json()

    logging.debug(f"Webhook received: {json.dumps(body, indent=2)[:500]}")

    # Facebook sends entries array
    for entry in body.get("entry", []):
        for messaging in entry.get("messaging", []):
            sender_id = messaging.get("sender", {}).get("id")

            # Skip if from our bot or no sender
            if not sender_id:
                continue

            # ── Handle text message ──
            if "message" in messaging and "text" in messaging["message"]:
                user_text = messaging["message"]["text"]

                # Show typing indicator
                send_typing(sender_id)

                # Get product context
                context = product_db.get_context()

                # Ask AI with conversation history
                history = conversations.get(sender_id, [])
                reply = ask_ai(user_text, context, history=history)

                # Track conversation for order extraction
                track_conversation(sender_id, user_text, reply)

                # Check if order was confirmed — save it
                if is_order_confirmed(reply):
                    conv_text = "\n".join(f"{'👤' if m['role']=='user' else '🤖'}: {m['content']}" for m in history[-10:])
                    info = extract_order_info(conv_text)
                    if info:
                        order = order_db.add_order(
                            name=info["name"],
                            phone=info["phone"],
                            address=info["address"],
                            product=info.get("product", "N/A"),
                            sender_id=sender_id
                        )
                        logging.info(f"✅ Order saved: {order['id']} — {info['name']}")

                # Send reply
                send_message(sender_id, reply)

            # ── Handle image message ──
            elif "message" in messaging and "attachments" in messaging["message"]:
                for attachment in messaging["message"]["attachments"]:
                    if attachment["type"] == "image":
                        image_url = attachment["payload"].get("url", "")
                        if image_url:
                            send_typing(sender_id)

                            # Analyze image
                            vision_result = analyze_image(image_url)

                            # Check if product is recognized
                            context = product_db.get_context()
                            history = conversations.get(sender_id, [])
                            reply = ask_ai(
                                f"গ্রাহক একটি ছবি পাঠিয়েছে। ছবি থেকে যা বোঝা গেছে: {vision_result}\n\n"
                                f"ছবির পণ্য সম্পর্কে বাংলায় বিস্তারিত তথ্য দিন এবং দাম জানান।",
                                context, history=history
                            )

                            track_conversation(sender_id, f"[ছবি] {vision_result[:100]}", reply)
                            send_message(sender_id, reply)

    return {"status": "ok"}


@app.post("/webhook-updates")
async def handle_updates(request: Request):
    """Alternative webhook endpoint for newer Meta APIs"""
    body = await request.json()
    logging.info(f"Updates webhook: {json.dumps(body, indent=2)[:500]}")

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == "messages":
                value = change.get("value", {})

                sender_id = value.get("sender", {}).get("id")
                message = value.get("message", {})

                if not sender_id:
                    continue

                # Handle text
                if message.get("text"):
                    user_text = message["text"]
                    send_typing(sender_id)

                    context = product_db.get_context()
                    history = conversations.get(sender_id, [])
                    reply = ask_ai(user_text, context, history=history)
                    track_conversation(sender_id, user_text, reply)

                    # Check if order was confirmed
                    if is_order_confirmed(reply):
                        conv_text = "\n".join(f"{'👤' if m['role']=='user' else '🤖'}: {m['content']}" for m in history[-10:])
                        info = extract_order_info(conv_text)
                        if info:
                            order = order_db.add_order(name=info["name"], phone=info["phone"], address=info["address"], product=info.get("product","N/A"), sender_id=sender_id)
                            logging.info(f"✅ Order saved (updates): {order['id']} — {info['name']}")

                    send_message(sender_id, reply)

                # Handle attachments (images)
                for attachment in message.get("attachments", []):
                    if attachment.get("type") == "image":
                        image_url = attachment.get("payload", {}).get("url", "")
                        if image_url:
                            send_typing(sender_id)
                            vision_result = analyze_image(image_url)
                            context = product_db.get_context()
                            history = conversations.get(sender_id, [])
                            reply = ask_ai(
                                f"গ্রাহক একটি ছবি পাঠিয়েছে: {vision_result}। পণ্য সম্পর্কে বাংলায় জানান।",
                                context, history=history
                            )
                            track_conversation(sender_id, f"[ছবি] {vision_result[:100]}", reply)
                            send_message(sender_id, reply)

    return {"status": "ok"}


# ─── Main ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    logging.info("🤖 Starting Facebook Messenger Bot...")
    logging.info(f"📦 Loaded {len(product_db.products)} products")
    logging.info(f"🔜 {len(product_db.upcoming)} upcoming products")
    logging.info(f"🌍 Dashboard: {CONFIG['PUBLIC_URL']}")

    uvicorn.run(app, host=CONFIG["HOST"], port=CONFIG["PORT"])
