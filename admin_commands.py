from telegram_api import send_message


class AdminMixin:
    """Админ-команды: права владельца, рассылка, перезагрузка, выдача ресурсов."""

    def _is_owner(self, chat_id):
        from config import OWNER_CHAT_ID
        if chat_id != OWNER_CHAT_ID:
            send_message(chat_id, "⛔ У вас нет прав на это действие.")
            return False
        return True

    def _broadcast(self, chat_id, text):
        """Рассылка сообщения всем сохранённым пользователям. Только владелец."""
        if not self._is_owner(chat_id):
            return
        msg = text[len("/broadcast"):].strip()
        if not msg:
            send_message(chat_id, "Формат: /broadcast <текст>")
            return
        sent, failed = 0, 0
        for uid, prof in self.store.users.items():
            if not prof.get('nickname'):
                continue
            result = send_message(uid, f"📢 <b>Объявление</b>\n\n{msg}")
            if result and result.get('ok'):
                sent += 1
            else:
                failed += 1
        send_message(chat_id, f"✅ Рассылка завершена: отправлено {sent}, ошибок {failed}.")

    def _reload_data(self, chat_id):
        """Перечитывает данные пользователей и каталоги с диска. Только владелец."""
        if not self._is_owner(chat_id):
            return
        n_users = self.store.reload()
        self.games.reload()
        send_message(chat_id, f"🔄 Данные перечитаны: пользователей {n_users}, каталоги карт/наборов/кодов обновлены.")

    def _add_coins(self, chat_id, text):
        """/addcoins <кол-во> — начислить монеты себе (владельцу)."""
        if not self._is_owner(chat_id):
            return
        parts = text[len("/addcoins"):].strip().split()
        if len(parts) != 1:
            send_message(chat_id, "Формат: /addcoins <кол-во>")
            return
        try:
            amount = int(parts[0])
        except ValueError:
            send_message(chat_id, "Количество монет должно быть целым.")
            return
        new_balance = self.store.add_coins(chat_id, amount)
        send_message(chat_id, f"✅ Начислено {amount} монет. Баланс: {new_balance} 🪙")

    def _resolve_target_player(self, key):
        """Находит профиль игрока по нику или chat_id. Возвращает (uid, prof) или (None, None)."""
        for uid, prof in list(self.store.users.items()):
            if uid == key or prof.get('nickname') == key:
                return uid, prof
        return None, None

    def _give_card(self, chat_id, text):
        """/givecard <ник или id> <карта> — начислить карту игроку."""
        if not self._is_owner(chat_id):
            return
        parts = text[len("/givecard"):].strip().split(None, 1)
        if len(parts) != 2:
            send_message(chat_id, "Формат: /givecard <ник или id> <карта>")
            return
        key, card_name = parts[0], parts[1].strip()
        uid, prof = self._resolve_target_player(key)
        if prof is None:
            send_message(chat_id, f"Игрок «{key}» не найден.")
            return
        target_cid = None
        for cid, info in self.games.cards.items():
            if cid.lower() == card_name.lower() or info.get('name', '').lower() == card_name.lower():
                target_cid = cid
                break
        if target_cid is None:
            send_message(chat_id, f"Карта «{card_name}» не найдена.")
            return
        if not self.games.grant_card(prof, target_cid, 1):
            send_message(chat_id, "Внутренняя ошибка: карта не начислена.")
            return
        self.store.persist()
        send_message(chat_id, f"✅ {prof.get('nickname', key)}: начислена карта «{self.games.card_name(target_cid)}»")

    def _give_set(self, chat_id, text):
        """/giveset <ник или id> <набор> — начислить набор игроку."""
        if not self._is_owner(chat_id):
            return
        parts = text[len("/giveset"):].strip().split(None, 1)
        if len(parts) != 2:
            send_message(chat_id, "Формат: /giveset <ник или id> <набор>")
            return
        key, set_name = parts[0], parts[1].strip()
        uid, prof = self._resolve_target_player(key)
        if prof is None:
            send_message(chat_id, f"Игрок «{key}» не найден.")
            return
        target_set = None
        for sid, info in self.games.sets.items():
            if sid.lower() == set_name.lower() or info.get('name', '').lower() == set_name.lower():
                target_set = sid
                break
        if target_set is None:
            send_message(chat_id, f"Набор «{set_name}» не найден.")
            return
        if not self.games.grant_set(prof, target_set):
            send_message(chat_id, "Внутренняя ошибка: набор не начислен.")
            return
        self.store.persist()
        send_message(chat_id, f"✅ {prof.get('nickname', key)}: начислен набор «{self.games.set_name(target_set)}»")

    def _set_wins(self, chat_id, text):
        """/setwins <ник или id> <число> — установить победы. /setwins <число> — себе."""
        if not self._is_owner(chat_id):
            return
        from config import OWNER_CHAT_ID
        parts = text[len("/setwins"):].strip().split()
        if len(parts) == 1:
            key = str(OWNER_CHAT_ID)
            val = parts[0]
        elif len(parts) == 2:
            key, val = parts
        else:
            send_message(chat_id, "Формат: /setwins <ник или id> <число>, или /setwins <число> — себе")
            return
        try:
            val = int(val)
        except ValueError:
            send_message(chat_id, "Число побед должно быть целым.")
            return
        uid, prof = self._resolve_target_player(key)
        if prof is None:
            send_message(chat_id, f"Игрок «{key}» не найден.")
            return
        self.store.users[uid]['wins'] = val
        self.store.persist()
        nick = prof.get('nickname', key)
        send_message(chat_id, f"✅ {nick}: победы установлены = {val}")