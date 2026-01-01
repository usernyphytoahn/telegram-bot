#!/usr/bin/env python3
import os
import requests
import json
import time
import threading
from flask import Flask, request

app = Flask(__name__)

API_URL = "https://dpzavygtlycvlxlhxxtf.supabase.co/functions/v1/bot-api"
API_TOKEN = "mito1546742wddagesercret"

BOTS = {}
PRODUCTS = {}
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

def load_bots():
    global BOTS
    result = api_request("/bots")
    if result and result.get("success"):
        bots_list = result.get("data", [])
        for bot in bots_list:
            token = bot.get("bot_token")
            if token:
                BOTS[token] = {
                    "id": bot.get("id"),
                    "nombre": bot.get("nombre"),
                    "grupo": bot.get("grupo_notificaciones"),
                    "token": token
                }
        print(f"Loaded {len(BOTS)} bots")
    return BOTS

def load_products(bot_token):
    result = api_request(f"/productos?bot_token={bot_token}")
    if result and result.get("success"):
        PRODUCTS[bot_token] = result.get("data", [])
    return PRODUCTS.get(bot_token, [])

def get_link(producto_id, user_id, username):
    result = api_request(f"/links/{producto_id}?user_id={user_id}&username={username}")
    if result and result.get("success"):
        return result.get("data", {}).get("link")
    return None

def register_purchase(producto_id, user_id, username, sck, link):
    return api_request("/compras", method="POST", data={"producto_id": producto_id, "user_id": str(user_id), "username": username, "sck": sck, "link_entregado": link})

def tg(token, method, data=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        if data:
            return requests.post(url, json=data, timeout=10)
        return requests.get(url, timeout=10)
    except:
        return None

def send_message(token, chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    tg(token, "sendMessage", data)

def send_photo(token, chat_id, photo, caption, reply_markup=None):
    data = {"chat_id": chat_id, "photo": photo, "caption": caption, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    tg(token, "sendPhoto", data)

def get_keyboard(bot_token):
    products = PRODUCTS.get(bot_token, [])
    if not products:
        products = load_products(bot_token)
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

def show_welcome(token, chat_id, name):
    send_message(token, chat_id, f"Welcome, {name}!\n\nSelect a product below.", get_keyboard(token))

def show_product(token, chat_id, product):
    caption = f"<b>{product.get('nombre')}</b>\nPrice: ${product.get('precio')} {product.get('moneda', 'USD')}"
    buttons = {"inline_keyboard": [[{"text": "Buy Now", "callback_data": f"buy_{product.get('id')}"}]]}
    if product.get("imagen_url"):
        send_photo(token, chat_id, product.get("imagen_url"), caption, buttons)
    else:
        send_message(token, chat_id, caption, buttons)

def find_product(bot_token, name):
    products = PRODUCTS.get(bot_token, [])
    if not products:
        products = load_products(bot_token)
    for p in products:
        if p.get("nombre", "").lower() == name.lower():
            return p
    return None

def find_product_by_id(bot_token, prod_id):
    products = PRODUCTS.get(bot_token, [])
    if not products:
        products = load_products(bot_token)
    for p in products:
        if p.get("id") == prod_id:
            return p
    return None

def process_purchase(token, chat_id, user_id, username, first_name, prod_id):
    product = find_product_by_id(token, prod_id)
    if not product:
        send_message(token, chat_id, "Product not found.")
        return
    sck = f"tg_{user_id}_{prod_id}_{int(time.time())}"
    hotmart = product.get("hotmart_link", "")
    if not hotmart:
        send_message(token, chat_id, "Payment link not available.")
        return
    PENDING[sck] = {"token": token, "chat_id": chat_id, "user_id": user_id, "username": username, "first_name": first_name, "producto_id": prod_id, "producto_nombre": product.get("nombre")}
    link = f"{hotmart}?sck={sck}"
    msg = f"<b>{product.get('nombre')}</b>\nPrice: ${product.get('precio')} {product.get('moneda', 'USD')}\n\nYour payment link:\n{link}\n\nThis link is unique to you.\nAfter payment, you'll receive your access here."
    send_message(token, chat_id, msg, {"inline_keyboard": [[{"text": "Pay Now", "url": link}]]})
    bot = BOTS.get(token, {})
    grupo = bot.get("grupo")
    if grupo:
        send_message(token, grupo, f"<b>NEW LINK</b>\n\nUser: @{username if username else first_name}\nProduct: {product.get('nombre')}\nSCK: <code>{sck}</code>")

def deliver_product(sck):
    if sck not in PENDING:
        return
    c = PENDING[sck]
    token = c["token"]
    link = get_link(c["producto_id"], c["user_id"], c.get("username", ""))
    if not link:
        send_message(token, c["chat_id"], "Payment received!\n\nWe're preparing your access.")
        bot = BOTS.get(token, {})
        grupo = bot.get("grupo")
        if grupo:
            send_message(token, grupo, f"<b>NO LINKS</b>\n\nProduct: {c['producto_nombre']}\nClient: {c['first_name']}")
        return
    send_message(token, c["chat_id"], f"🎉 <b>PAYMENT CONFIRMED!</b>\n\nThank you for purchasing <b>{c['producto_nombre']}</b>\n\n🔗 <b>Your access:</b>\n{link}\n\n⚠️ Single use only.", {"inline_keyboard": [[{"text": "Access Now", "url": link}]]})
    register_purchase(c["producto_id"], c["user_id"], c.get("username", ""), sck, link)
    bot = BOTS.get(token, {})
    grupo = bot.get("grupo")
    if grupo:
        send_message(token, grupo, f"<b>SALE COMPLETED</b>\n\nClient: {c['first_name']}\nProduct: {c['producto_nombre']}")
    del PENDING[sck]

def handle_update(token, data):
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        user_id = msg["from"]["id"]
        username = msg["from"].get("username", "")
        first_name = msg["from"].get("first_name", "User")
        text = msg.get("text", "").strip()
        if text.lower() == "/start":
            load_products(token)
            show_welcome(token, chat_id, first_name)
        else:
            product = find_product(token, text)
            if product:
                show_product(token, chat_id, product)
            else:
                show_welcome(token, chat_id, first_name)
    elif "callback_query" in data:
        cb = data["callback_query"]
        tg(token, "answerCallbackQuery", {"callback_query_id": cb["id"]})
        chat_id = cb["message"]["chat"]["id"]
        user_id = cb["from"]["id"]
        username = cb["from"].get("username", "")
        first_name = cb["from"].get("first_name", "User")
        cb_data = cb.get("data", "")
        if cb_data.startswith("buy_"):
            process_purchase(token, chat_id, user_id, username, first_name, cb_data.replace("buy_", ""))

@app.route("/webhook/<token>", methods=["POST"])
def telegram_webhook(token):
    if token in BOTS:
        data = request.get_json()
        if data:
            handle_update(token, data)
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
    return f"Bot Active - {len(BOTS)} bots loaded"

@app.route("/reload", methods=["GET"])
def reload_bots():
    setup_all_webhooks()
    return f"Reloaded - {len(BOTS)} bots"

def setup_all_webhooks():
    load_bots()
    railway_url = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
    if not railway_url:
        railway_url = "telegram-bot-production-64f7.up.railway.app"
    for token in BOTS:
        webhook_url = f"https://{railway_url}/webhook/{token}"
        tg(token, "setWebhook", {"url": webhook_url})
        print(f"Webhook set for {BOTS[token]['nombre']}: {webhook_url}")
        load_products(token)

setup_all_webhooks()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
