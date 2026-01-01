#!/usr/bin/env python3
import os
import requests
import json
import time
from datetime import datetime
from flask import Flask, request

app = Flask(__name__)

API_URL = "https://dpzavygtlycvlxlhxxtf.supabase.co/functions/v1/bot-api"
API_TOKEN = "mito1546742wddagesercret"
TELEGRAM_BOT_TOKEN = None
GRUPO_NOTIFICACIONES = None
PRODUCTS_CACHE = []
PENDING = {}

def api_request(endpoint, method="GET", data=None):
    headers = {"x-bot-token": API_TOKEN, "Content-Type": "application/json"}
    url = f"{API_URL}{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=10)
        else:
            resp = requests.post(url, headers=headers, json=data, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return None

def load_config():
    global TELEGRAM_BOT_TOKEN, GRUPO_NOTIFICACIONES
    result = api_request("/config")
    if result and result.get("success"):
        config = result.get("data", {})
        TELEGRAM_BOT_TOKEN = config.get("bot_token")
        GRUPO_NOTIFICACIONES = config.get("grupo_notificaciones")
        return True
    return False

def get_products():
    global PRODUCTS_CACHE
    result = api_request("/productos")
    if result and result.get("success"):
        PRODUCTS_CACHE = result.get("data", [])
    return PRODUCTS_CACHE

def get_link(producto_id, user_id, username):
    result = api_request(f"/links/{producto_id}?user_id={user_id}&username={username}")
    if result and result.get("success"):
        return result.get("data", {}).get("link")
    return None

def register_purchase(producto_id, user_id, username, sck, link):
    return api_request("/compras", method="POST", data={"producto_id": producto_id, "user_id": str(user_id), "username": username, "sck": sck, "link_entregado": link})

def tg(method, data=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        if data:
            return requests.post(url, json=data, timeout=10)
        return requests.get(url, timeout=10)
    except:
        return None

def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    tg("sendMessage", data)

def send_photo(chat_id, photo, caption, reply_markup=None):
    data = {"chat_id": chat_id, "photo": photo, "caption": caption, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    tg("sendPhoto", data)

def get_keyboard():
    products = PRODUCTS_CACHE if PRODUCTS_CACHE else get_products()
    keyboard = []
    row = []
    for p in products:
        row.append({"text": p.get("nombre", "")})
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return {"keyboard": keyboard, "resize_keyboard": True}

def show_welcome(chat_id, name):
    send_message(chat_id, f"Welcome, {name}!\n\nSelect a product below.", get_keyboard())

def show_product(chat_id, product):
    caption = f"<b>{product.get('nombre')}</b>\nPrice: ${product.get('precio')} {product.get('moneda', 'USD')}"
    buttons = {"inline_keyboard": [[{"text": "Buy Now", "callback_data": f"buy_{product.get('id')}"}]]}
    if product.get("imagen_url"):
        send_photo(chat_id, product.get("imagen_url"), caption, buttons)
    else:
        send_message(chat_id, caption, buttons)

def find_product(name):
    for p in PRODUCTS_CACHE:
        if p.get("nombre", "").lower() == name.lower():
            return p
    return None

def process_purchase(chat_id, user_id, username, first_name, prod_id):
    product = None
    for p in PRODUCTS_CACHE:
        if p.get("id") == prod_id:
            product = p
            break
    if not product:
        send_message(chat_id, "Product not found.")
        return
    sck = f"tg_{user_id}_{prod_id}_{int(time.time())}"
    hotmart = product.get("hotmart_link", "")
    if not hotmart:
        send_message(chat_id, "Payment link not available.")
        return
    PENDING[sck] = {"chat_id": chat_id, "user_id": user_id, "username": username, "first_name": first_name, "producto_id": prod_id, "producto_nombre": product.get("nombre")}
    link = f"{hotmart}?sck={sck}"
    msg = f"<b>{product.get('nombre')}</b>\nPrice: ${product.get('precio')} {product.get('moneda', 'USD')}\n\nYour payment link:\n{link}\n\nThis link is unique to you.\nAfter payment, you'll receive your access here."
    send_message(chat_id, msg, {"inline_keyboard": [[{"text": "Pay Now", "url": link}]]})
    if GRUPO_NOTIFICACIONES:
        send_message(GRUPO_NOTIFICACIONES, f"<b>NEW LINK</b>\n\nUser: @{username if username else first_name}\nProduct: {product.get('nombre')}\nSCK: <code>{sck}</code>")

def deliver_product(sck):
    if sck not in PENDING:
        return
    c = PENDING[sck]
    link = get_link(c["producto_id"], c["user_id"], c.get("username", ""))
    if not link:
        send_message(c["chat_id"], "Payment received!\n\nWe're preparing your access.")
        if GRUPO_NOTIFICACIONES:
            send_message(GRUPO_NOTIFICACIONES, f"<b>NO LINKS</b>\n\nProduct: {c['producto_nombre']}\nClient: {c['first_name']}")
        return
    send_message(c["chat_id"], f"🎉 <b>PAYMENT CONFIRMED!</b>\n\nThank you for purchasing <b>{c['producto_nombre']}</b>\n\n🔗 <b>Your access:</b>\n{link}\n\n⚠️ Single use only.", {"inline_keyboard": [[{"text": "Access Now", "url": link}]]})
    register_purchase(c["producto_id"], c["user_id"], c.get("username", ""), sck, link)
    if GRUPO_NOTIFICACIONES:
        send_message(GRUPO_NOTIFICACIONES, f"<b>SALE COMPLETED</b>\n\nClient: {c['first_name']}\nProduct: {c['producto_nombre']}")
    del PENDING[sck]

def handle_message(msg):
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    username = msg["from"].get("username", "")
    first_name = msg["from"].get("first_name", "User")
    text = msg.get("text", "").strip()
    if text.lower() == "/start":
        show_welcome(chat_id, first_name)
    else:
        product = find_product(text)
        if product:
            show_product(chat_id, product)
        else:
            show_welcome(chat_id, first_name)

def handle_callback(cb):
    tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
    chat_id = cb["message"]["chat"]["id"]
    user_id = cb["from"]["id"]
    username = cb["from"].get("username", "")
    first_name = cb["from"].get("first_name", "User")
    data = cb.get("data", "")
    if data.startswith("buy_"):
        process_purchase(chat_id, user_id, username, first_name, data.replace("buy_", ""))

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if "message" in data:
        handle_message(data["message"])
    elif "callback_query" in data:
        handle_callback(data["callback_query"])
    return "ok"

@app.route("/hotmart", methods=["POST"])
def hotmart_webhook():
    data = request.get_json()
    sck = None
    status = None
    if "data" in data:
        p = data["data"].get("purchase", {})
        sck = p.get("origin", {}).get("sck")
        status = p.get("status")
    if sck and status in ["APPROVED", "COMPLETE"]:
        deliver_product(sck)
    return "ok"

@app.route("/", methods=["GET"])
def home():
    return "Bot Active"

def setup_webhook(url):
    tg("setWebhook", {"url": f"{url}/telegram"})

if __name__ == "__main__":
    load_config()
    get_products()
    port = int(os.environ.get("PORT", 5000))
    railway_url = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
    if railway_url:
        setup_webhook(f"https://{railway_url}")
    app.run(host="0.0.0.0", port=port)
