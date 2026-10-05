import random
import battle
from cards import BattleError


class MatchManager:
    """Держит активные партии. Ключ — короткий код вступления."""
    CODES = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    def __init__(self):
        self.matches = {}          # code -> Match
        self._by_chat = {}         # chat_id -> code

    def _gen_code(self):
        while True:
            code = ''.join(random.choices(self.CODES, k=4))
            if code not in self.matches:
                return code

    def create(self, chat_id, nickname):
        """Создаёт партию и возвращает код. Игрок не должен уже состоять в другой партии."""
        if chat_id in self._by_chat:
            raise BattleError("⛔ Вы уже в другой партии. Досрочно завершите её, чтобы начать новую.")
        code = self._gen_code()
        self.matches[code] = {
            "p1": chat_id,
            "p1_name": nickname,
            "p2": None,
            "p2_name": None,
            "game": None,
            "attack_state": None,
        }
        self._by_chat[chat_id] = code
        return code

    def join(self, code, chat_id, nickname):
        """Присоединение вторым игроком. Возвращает (ok, сообщение)."""
        if chat_id in self._by_chat:
            return False, "❌ Вы уже в другой партии. Досрочно завершите её, чтобы вступить в новую."
        key = code.strip().upper()
        m = self.matches.get(key)
        if not m:
            return False, "❌ Игра с таким кодом не найдена."
        if m["p2"] is not None:
            return False, "❌ В этой игре уже есть два игрока."
        if m["p1"] == chat_id:
            return False, "❌ Вы не можете присоединиться к своей же игре."
        m["p2"] = chat_id
        m["p2_name"] = nickname
        self._by_chat[chat_id] = key
        return True, "ok"

    def match_of(self, chat_id):
        code = self._by_chat.get(chat_id)
        return code, self.matches.get(code)

    def start_game(self, code, deck1=None, deck2=None, hero1=None, hero2=None):
        """Создаёт движок и раздаёт карты. deck/hero — сохранённые настройки игроков (могут быть None)."""
        m = self.matches[code]
        g = battle.Game(m["p1_name"], m["p2_name"], seed=random.randint(1, 999999),
                        deck1=deck1, deck2=deck2, hero1=hero1, hero2=hero2)
        m["game"] = g
        g.start()
        return g

    def drop(self, code):
        m = self.matches.pop(code, None)
        if m:
            self._by_chat.pop(m["p1"], None)
            if m["p2"]:
                self._by_chat.pop(m["p2"], None)

    def leave_for(self, chat_id):
        """Убирает игрока из всех активных партий и снимает их с него. Возвращает (код, соперник)."""
        code = self._by_chat.get(chat_id)
        if not code or code not in self.matches:
            self._by_chat.pop(chat_id, None)
            return None, None
        m = self.matches[code]
        opp = m["p1"] if m["p2"] == chat_id else m["p2"]  # соперник (может быть None до старта)
        self.drop(code)
        return code, opp

    def active_chat(self, code):
        """Возвращает chat_id игрока, чей сейчас ход."""
        m = self.matches[code]
        g = m["game"]
        return m["p1"] if g.turn == 1 else m["p2"]