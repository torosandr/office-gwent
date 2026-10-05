import time
from config import FILES
from storage import UserStore
from game_data import GameData
from telegram_api import api_request, answer_callback
from ui import build_menu
from handlers import Handlers

def main():
    store = UserStore(FILES["users"])
    games = GameData()
    handlers = Handlers(store, games, build_menu)

    print("Бот запущен (long polling).")
    offset = 0
    while True:
        try:
            data = api_request(
                "getUpdates",
                offset=offset,
                timeout=30,
                allowed_updates=["message", "callback_query"],
            )
            if not data or not data.get("ok"):
                time.sleep(2)
                continue

            for update in data["result"]:
                update_id = update.get("update_id")
                offset = update_id + 1

                if "message" in update:
                    msg = update["message"]
                    chat_id = msg["chat"]["id"]
                    if "text" in msg:
                        handlers.handle_text(chat_id, msg["text"])

                elif "callback_query" in update:
                    cb = update["callback_query"]
                    chat_id = cb["message"]["chat"]["id"]
                    message_id = cb["message"]["message_id"]
                    data = cb.get("data", "")
                    answer_callback(cb["id"])
                    handlers.handle_callback(chat_id, message_id, data)

        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()