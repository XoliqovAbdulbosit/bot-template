import os
import time
import json
import sqlite3
import requests
import threading  # New: Used for non-blocking delayed tasks
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# --- Configuration & Setup ---
# Load environment variables from .env file
load_dotenv()

# Get the bot token from environment variables
# Added a check to ensure the token is present
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError(
        "BOT_TOKEN environment variable not set. Please check your .env file."
    )

# Base URL for Telegram Bot API
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
DB_FILE = "bot_data.db"
CONTACTS_FILE = "contacts.json"

# --- Flask App Setup ---
app = Flask(__name__)
# Enable Cross-Origin Resource Sharing
CORS(app)

# --- Global State Variables ---
# Customizable response/state dictionary
RESPONSES_MAP = {
    "/start": {
        "text": "Hello! Welcome to the bot!\n\nWhat would you like to do?",
        "buttons": ["Option A", "Option B", "Register"],
    },
    "Option A": {"text": "You chose Option A. This is the resulting message."},
    "Option B": {"text": "You chose Option B. This is the resulting message."},
    "Register": {
        "text": "To register, please send your Name and Phone number in the format: **John +123456789012**"
    },
    # Added a state to mark the user is expecting structured input
    "WAITING_FOR_CONTACT": {
        "text": "Thank you, I'm expecting your contact details now. Format: Name +PhoneNumber"
    },
    "sequential_step_1": {
        "text": "Answer the first question:",
        "buttons": ["Yes", "No"],
    },
    # Changed 'then' to be handled by a non-blocking thread
    "sequential_step_2": {
        "text": "Thank you for your answer!",
        "follow_up": "Here is a follow-up message after a short delay.",
    },
    "final_action": {
        "text": "Test completed. Join our channel: [Link](https://t.me/example)"
    },
}

# Dictionary to manage custom user data or state (e.g., tracking current quiz step or expected input)
# user_states now handles the input queue state better: {chat_id: 'WAITING_FOR_CONTACT'}
user_states = {}
# input_queue is replaced by user_states for better state management

# --- Utility Functions: Data Storage ---


def load_data_from_json(filename):
    """Loads data from a JSON file."""
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_data_to_json(data, filename):
    """Saves data to a JSON file."""
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=4)
    except IOError as e:
        print(f"Error saving data to {filename}: {e}")


def save_chat_ids(chat_id, filename="chat_ids.json"):
    """Adds a chat ID to a list stored in a JSON file."""
    chat_ids = load_data_from_json(filename).get("chat_ids", [])
    if chat_id not in chat_ids:
        chat_ids.append(chat_id)
        save_data_to_json({"chat_ids": chat_ids}, filename)


def save_user_contact(id, name, phone_number):
    """Saves a user's contact info to a JSON file."""
    data = load_data_from_json(CONTACTS_FILE)
    data[str(id)] = {"name": name, "phone": phone_number, "timestamp": time.time()}
    save_data_to_json(data, CONTACTS_FILE)


# --- Utility Functions: Telegram API Communication ---


def send_telegram_message(chat_id, reply):
    """
    Sends a message, photo, or document to a Telegram chat.
    Handles markdown parsing and inline keyboard buttons.
    """
    if (
        not reply
        or not reply.get("text")
        and not reply.get("photo")
        and not reply.get("file")
    ):
        print(f"Warning: Attempted to send empty reply to {chat_id}")
        return

    # --- Media Handling (Photo/File) ---
    if reply.get("photo") or reply.get("file"):
        media_type = "photo" if reply.get("photo") else "document"
        file_key = reply.get("photo") or reply.get("file")
        url = f"{BASE_URL}/send{media_type.capitalize()}"

        current_directory = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_directory, file_key)

        try:
            with open(file_path, "rb") as media_file:
                files = {media_type: media_file}
                data = {
                    "chat_id": chat_id,
                    "caption": reply.get("text", ""),
                    "parse_mode": "Markdown",
                }
                response = requests.post(
                    url, files=files, data=data, timeout=10
                )  # Added timeout
                response.raise_for_status()  # Check for bad status code

            # Use threading for non-blocking sequential messages
            if reply.get("follow_up"):
                threading.Timer(
                    3.0, send_delayed_message, args=[chat_id, reply.get("follow_up")]
                ).start()

            return  # Exit after sending media

        except FileNotFoundError:
            print(f"Error: Media file not found at {file_path}")
            # Fallback to sending just text without recursion
            send_telegram_message(
                chat_id,
                {
                    "text": f"⚠️ Media file not found for `{file_key}`. {reply.get('text', 'Placeholder message.')}"
                },
            )
            return
        except requests.RequestException as e:
            print(f"Error sending media via Telegram API: {e}")
            return

    # --- Text Message Handling ---
    url = f"{BASE_URL}/sendMessage"
    reply_markup = None

    if reply.get("buttons"):
        # Create inline keyboard from the list of button texts
        keyboard = [
            [{"text": button, "callback_data": button}] for button in reply["buttons"]
        ]
        reply_markup = {"inline_keyboard": keyboard}

    # Payload for sendMessage
    payload = {
        "chat_id": chat_id,
        "text": reply["text"],
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        # Send the main message
        response = requests.post(url, json=payload, timeout=10)  # Added timeout
        response.raise_for_status()  # Check for bad status code

        # Use threading for non-blocking sequential messages
        if reply.get("follow_up"):
            # Start a new thread to send the follow-up message after 3 seconds
            threading.Timer(
                3.0, send_delayed_message, args=[chat_id, reply.get("follow_up")]
            ).start()

    except requests.RequestException as e:
        print(f"Error sending message via Telegram API: {e}")


def send_delayed_message(chat_id, text):
    """Function executed in a separate thread to send a message after a delay."""
    # This function is now non-blocking to the main Flask thread
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        response = requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error sending delayed message: {e}")


# --- Webhook Endpoint ---


@app.route("/bot", methods=["POST"])
def telegram_webhook():
    """Handles incoming updates from the Telegram webhook."""
    data = request.json

    if "callback_query" in data:
        # --- Handle Button Presses (Callback Queries) ---
        query = data["callback_query"]
        chat_id = query["message"]["chat"]["id"]
        callback_data = query["data"]

        # Acknowledge the callback query to remove the 'loading' state on the button
        requests.post(
            f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": query["id"]}
        )

        # Transition for the 'Register' button to set the state
        if callback_data == "Register":
            user_states[chat_id] = "WAITING_FOR_CONTACT"
            send_telegram_message(chat_id, RESPONSES_MAP["Register"])

        elif callback_data in RESPONSES_MAP:
            send_telegram_message(chat_id, RESPONSES_MAP[callback_data])
        else:
            send_telegram_message(
                chat_id, {"text": f"Unknown option: `{callback_data}`\n\nTry /start"}
            )

    elif "message" in data:
        # --- Handle Incoming Messages (Text, Contact, etc.) ---
        message = data["message"]
        chat_id = message["chat"]["id"]
        message_text = message.get("text", "")

        # Save chat ID for tracking purposes
        save_chat_ids(chat_id)

        # Check if the user is in a specific input state
        if user_states.get(chat_id) == "WAITING_FOR_CONTACT":
            # --- Handle User Input for Registration ---

            # Basic validation: Expecting "Name +123456789012"
            try:
                parts = message_text.split(maxsplit=1)
                if len(parts) == 2:
                    name = parts[0]
                    phone_number = parts[1]

                    # More robust check: starts with +, has exactly 12 digits after the +
                    if (
                        phone_number.startswith("+")
                        and phone_number[1:].isdigit()
                        and len(phone_number) == 13
                    ):
                        # Process and save the contact info
                        save_user_contact(chat_id, name, phone_number)
                        send_telegram_message(
                            chat_id,
                            {
                                "text": f"✅ Information for **{name}** received and saved. Phone: `{phone_number}`"
                            },
                        )

                        # Clear state and return to main menu
                        del user_states[chat_id]
                        send_telegram_message(chat_id, RESPONSES_MAP["/start"])
                        return

                # If validation fails
                send_telegram_message(
                    chat_id,
                    {
                        "text": "⚠️ Invalid format. Please try again using: **Name +123456789012**"
                    },
                )

            except Exception as e:
                print(f"Registration error for {chat_id}: {e}")
                send_telegram_message(
                    chat_id,
                    {
                        "text": "An unexpected error occurred during registration. Try again."
                    },
                )

        elif message_text == "/start":
            # --- Handle the /start Command ---
            # Ensure any waiting state is cleared on /start
            if chat_id in user_states:
                del user_states[chat_id]
            send_telegram_message(chat_id, RESPONSES_MAP["/start"])

        elif message_text in RESPONSES_MAP:
            # --- Handle Other Known Commands or Text Triggers ---
            send_telegram_message(chat_id, RESPONSES_MAP[message_text])

        else:
            # --- Default Response for Unrecognized Input ---
            send_telegram_message(
                chat_id,
                {
                    "text": "I didn't understand that. Please use the buttons or type /start."
                },
            )

    return jsonify({"success": True})


# --- Database Initialization and Flask API Endpoints ---


def init_db():
    """Initializes the SQLite database and creates the users table."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS users
                    (id INTEGER PRIMARY KEY, full_name TEXT, phone_number TEXT)"""
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"Database initialization error: {e}")


@app.route("/submit", methods=["POST"])
def submit_data():
    """API endpoint to receive and store generic data via a POST request."""
    try:
        data = request.get_json()

        if not data or "full_name" not in data or "phone_number" not in data:
            return jsonify({"success": False, "message": "Missing data fields"}), 400

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Using a proper parameterized query to prevent SQL injection
        c.execute(
            "INSERT INTO users (full_name, phone_number) VALUES (?, ?)",
            (data["full_name"], data["phone_number"]),
        )
        conn.commit()
        conn.close()

        return jsonify({"success": True, "message": "Data submitted successfully"})
    except sqlite3.Error as e:
        return jsonify({"success": False, "error": f"Database error: {e}"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/data", methods=["GET"])
def get_data():
    """API endpoint to retrieve all data from the users table."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT * FROM users")

        columns = [description[0] for description in c.description]
        rows = c.fetchall()
        conn.close()

        data_list = [dict(zip(columns, row)) for row in rows]

        return jsonify(data_list)
    except sqlite3.Error as e:
        return jsonify({"success": False, "error": f"Database error: {e}"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- Application Entry Point ---

if __name__ == "__main__":
    init_db()  # Ensure the database is ready
    # Note: For production deployment, use a proper WSGI server (Gunicorn, Waitress)
    # and set debug=False.
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
