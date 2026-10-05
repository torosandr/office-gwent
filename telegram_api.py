import json
import atexit
import requests
from config import API_BASE, NO_PROXY

_session = requests.Session()
atexit.register(_session.close)

def api_request(method, **params):
    """Универсальный вызов Telegram Bot API."""
    url = f"{API_BASE}/{method}"
    json_data = {k: v for k, v in params.items() if v is not None}
    try:
        # Long polling может ждать 30 секунд на сервере; оставляем запас на ответ.
        read_timeout = params.get('timeout', 30) + 5 if method == 'getUpdates' else 30
        resp = _session.post(url, json=json_data, timeout=(5, read_timeout), proxies=NO_PROXY)
        return resp.json()
    except Exception as e:
        print(f"API error in {method}: {e}")
        return None

def send_message(chat_id, text, keyboard=None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard is not None:
        params["reply_markup"] = json.dumps({"inline_keyboard": keyboard})
    return api_request("sendMessage", **params)

def edit_message(chat_id, message_id, text, keyboard=None):
    params = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if keyboard is not None:
        params["reply_markup"] = json.dumps({"inline_keyboard": keyboard})
    return api_request("editMessageText", **params)

def answer_callback(callback_id):
    api_request("answerCallbackQuery", callback_query_id=callback_id)
