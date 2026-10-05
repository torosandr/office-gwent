import json
import os
from copy import deepcopy
from json_io import atomic_write_json
from config import FILES
from migrations import migrate_if_needed

def load(name):
    path = FILES[name]
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save(name, data):
    atomic_write_json(FILES[name], data)

DEFAULT_USER = {"nickname": "", "sets": [], "collection": {}, "state": "start", "wins": 0, "deck": [], "coins": 100, "hero": "режиссер"}

class UserStore:
    """
    Хранилище профилей пользователей.
    Профиль: {nickname, sets: [], collection: {card_id: count}, state}
    При загрузке автоматически мигрирует данные до текущей версии схемы.
    """
    def __init__(self, filename):
        self.file = filename
        self.users = self._load_file()

    def _load_file(self):
        if os.path.exists(self.file):
            data = migrate_if_needed(self.file)
            return {k: v for k, v in data.items() if k != "_version"}
        return {}

    def reload(self):
        """Перечитывает файл с диска в память (для ручных правок без рестарта)."""
        self.users = self._load_file()
        return len(self.users)

    def persist(self):
        from config import SCHEMA_VERSION
        out = dict(self.users)
        out["_version"] = SCHEMA_VERSION
        atomic_write_json(self.file, out)

    def get(self, chat_id):
        key = str(chat_id)
        if key not in self.users:
            self.users[key] = deepcopy(DEFAULT_USER)
            self.persist()
        prof = self.users[key]
        for k, v in DEFAULT_USER.items():
            if k not in prof:
                prof[k] = deepcopy(v)
        return prof

    def add_win(self, chat_id):
        prof = self.get(chat_id)
        prof['wins'] = prof.get('wins', 0) + 1
        self.persist()

    def award_win(self, chat_id, coins):
        """Сохраняет победу и награду одной записью."""
        prof = self.get(chat_id)
        previous_wins = prof.get('wins', 0)
        previous_coins = prof.get('coins', 0)
        prof['wins'] = previous_wins + 1
        prof['coins'] = previous_coins + coins
        try:
            self.persist()
        except Exception:
            prof['wins'] = previous_wins
            prof['coins'] = previous_coins
            raise

    def add_coins(self, chat_id, amount):
        prof = self.get(chat_id)
        prof['coins'] = prof.get('coins', 0) + amount
        self.persist()
        return prof['coins']

    def has_coins(self, chat_id, amount):
        prof = self.get(chat_id)
        return prof.get('coins', 0) >= amount

    def card_count(self, chat_id):
        prof = self.get(chat_id)
        return self._total_cards(prof)

    def _total_cards(self, prof):
        """Всего уникальных карт у игрока: базовые (есть у всех) + карты из коллекции (без дублей)."""
        from config import BASE_CARD_IDS
        return len(set(BASE_CARD_IDS) | set(prof.get('collection', {}).keys()))

    def ranking(self):
        """Игроки (ник, победы, карты) по убыванию побед."""
        rows = []
        for uid, prof in self.users.items():
            if not prof.get('nickname'):
                continue
            rows.append({
                "uid": uid,
                "nickname": prof['nickname'],
                "wins": prof.get('wins', 0),
                "cards": self._total_cards(prof),
                "coins": prof.get('coins', 0),
            })
        rows.sort(key=lambda r: (-r['wins'], -r['cards'], r['nickname']))
        return rows

    def id_of(self, user):
        """Возвращает chat_id по профилю user."""
        for uid, prof in self.users.items():
            if prof is user:
                return uid
        return "?"
