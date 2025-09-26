from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import requests
import os

app = Flask(__name__)
load_dotenv()

# 🔑 Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# 🗃️ Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 📌 User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.String(50), unique=True, nullable=False)

    def __repr__(self):
        return f"<User {self.telegram_id}>"

@app.route("/", methods=["GET"])
def home():
    return "Telegram bot is running!"

@app.route("/users", methods=["GET"])
def list_users():
    users = User.query.all()
    user_ids = [user.telegram_id for user in users]
    return {"user_ids": user_ids}

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()

    # Handle incoming messages
    if "message" in update:
        chat_id = str(update["message"]["chat"]["id"])
        text = update["message"].get("text", "")

        # Save user to database if not already present
        if not User.query.filter_by(telegram_id=chat_id).first():
            db.session.add(User(telegram_id=chat_id))
            db.session.commit()

        reply_text, keyboard = handle_logic(text)
        send_message(chat_id, reply_text, keyboard)

    # Handle button presses (callback queries)
    elif "callback_query" in update:
        callback_data = update["callback_query"]["data"]
        chat_id = str(update["callback_query"]["message"]["chat"]["id"])

        reply_text, keyboard = handle_logic(callback_data)
        send_message(chat_id, reply_text, keyboard)

    return {"ok": True}

def handle_logic(text: str):
    """Respond to user input with dynamic keyboard"""
    text = text.strip().lower()

    if text == "/start":
        return (
            "Salom! Quyidagilardan birini tanlang:",
            {
                "inline_keyboard": [
                    [{"text": "Bepul darslar", "callback_data": "free"}],
                    [{"text": "Darslarni davomi", "callback_data": "continue"}]
                ]
            }
        )
    elif text == "free":
        return ("Bepul darslar uchun havola: Link", None)
    elif text == "continue":
        return ("Darslarni davomini ko'rish uchun yozilish: Link", None)
    else:
        return ("Sizni tushunmadim. /start ni bosing.", None)

def send_message(chat_id, text, keyboard=None):
    """Send a message with optional inline keyboard"""
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if keyboard:
        payload["reply_markup"] = keyboard

    requests.post(url, json=payload)

def set_webhook():
    """Set Telegram webhook"""
    url = f"{TELEGRAM_API_URL}/setWebhook"
    payload = {"url": WEBHOOK_URL}
    response = requests.post(url, data=payload)
    print("SetWebhook response:", response.json())

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    set_webhook()
    app.run(host="0.0.0.0", port=5000)
