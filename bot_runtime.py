"""Текстовый бот в webhook-режиме, делит users.json с миниаппом в одном процессе."""
import os
import json
import threading
import requests
from config import FILES, TELEGRAM_TOKEN, API_BASE
from storage import UserStore
from game_data import GameData
from handlers import Handlers
from ui import build_menu
from bot_webhook import handle_update

NO_PROXY = {'http': None, 'https': None}


class BotRuntime:
    """Строит Handlers на общем users.json и обрабатывает апдейты из webhook."""

    def __init__(self):
        self.update_lock = threading.RLock()
        self.store = UserStore(FILES["users"])
        self.games = GameData()
        self.handlers = Handlers(self.store, self.games, build_menu)

    def handle_telegram(self, body):
        """Обрабатывает один апдейт от Telegram. body — dict из JSON запроса."""
        if not isinstance(body, dict):
            return None
        if 'update_id' not in body:
            return None
        with self.update_lock:
            handle_update(body, self.handlers)
        return None

    def set_webhook(self, url):
        """Прописывает webhook в Telegram. Возвращает (ok, message)."""
        resp = requests.post(
            f"{API_BASE}/setWebhook",
            json={"url": url, "allowed_updates": ["message", "callback_query"]},
            timeout=20, proxies=NO_PROXY,
        )
        try:
            data = resp.json()
            ok = bool(data.get('ok'))
            return ok, str(data.get('description', ''))
        except Exception:
            return False, 'Ошибка ответа Telegram.'


def build_bot_runtime():
    return BotRuntime() if TELEGRAM_TOKEN and 'ВАШ_ТОКЕН' not in TELEGRAM_TOKEN else None