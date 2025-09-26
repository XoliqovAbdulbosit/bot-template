from flask import Flask, request
import requests
import os

app = Flask(__name__)

# 🔑 Bot token and your public domain (must be HTTPS)
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://YOUR_DOMAIN/webhook")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


@app.route("/", methods=["GET"])
def home():
    return "Telegram bot is running!"


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()

    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")

        # Use logic handler
        reply_text = handle_logic(text)
        send_message(chat_id, reply_text)

    return {"ok": True}


def handle_logic(text: str) -> str:
    """Decide how to respond based on user input"""
    text = text.strip().lower()


def send_message(chat_id, text):
    """Send a message back to Telegram"""
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)


def set_webhook():
    """Automatically set webhook when app starts"""
    url = f"{TELEGRAM_API_URL}/setWebhook"
    payload = {"url": f"{WEBHOOK_URL}"}
    response = requests.post(url, data=payload)
    print("SetWebhook response:", response.json())


if __name__ == "__main__":
    # Set webhook before running the server
    set_webhook()
    app.run(host="0.0.0.0", port=5000)
