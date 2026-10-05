"""Обработка одного Telegram-апдейта (для webhook)."""


def handle_update(update, handlers):
    """Обрабатывает один апдейт (message или callback_query) через Handlers."""
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
        from telegram_api import answer_callback
        answer_callback(cb["id"])
        handlers.handle_callback(chat_id, message_id, data)
    return None