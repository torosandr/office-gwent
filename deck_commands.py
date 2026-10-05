from telegram_api import send_message, edit_message
from collections import Counter
from cards import copy_limit
from ui import (
    back_to_menu_button,
    deck_screen_text,
    deck_main_keyboard,
    deck_add_keyboard,
    deck_remove_keyboard,
)


class DeckMixin:
    """Настройка колоды: просмотр, добавление/удаление карт, сохранение."""

    def handle_deck(self, chat_id, message_id, data, user):
        deck = user.get('deck', [])
        action = data.split(":", 1)[1]

        if action == "main":
            edit_message(chat_id, message_id, deck_screen_text(deck), deck_main_keyboard())
            return
        if action == "add":
            coll = self.games.available_card_ids(user)
            if not coll:
                edit_message(chat_id, message_id, "Нет доступных карт для добавления.",
                             [back_to_menu_button()])
                return
            edit_message(chat_id, message_id,
                         f"Выберите карту (колода: {len(deck)}/15). Можно добавлять подряд — "
                         f"после «↩️ Назад» вернётесь в настройку.",
                         deck_add_keyboard(coll, deck))
            return
        if action == "remove":
            if not deck:
                edit_message(chat_id, message_id, "В колоде пока нет карт.", deck_main_keyboard())
                return
            edit_message(chat_id, message_id,
                         f"Какую карту убрать? ({len(deck)}/15)", deck_remove_keyboard(deck))
            return
        if action == "save":
            self.save_deck(chat_id, message_id, user, deck)
            return

        if action.startswith("addcard:"):
            if len(deck) >= 15:
                send_message(chat_id, "⛔ В колоде уже 15 карт — максимум.")
                return
            idx = int(action.split(":")[1])
            coll = self.games.available_card_ids(user)
            if not (0 <= idx < len(coll)):
                return
            card_id = coll[idx]
            limit = copy_limit(card_id)
            if deck.count(card_id) >= limit:
                send_message(chat_id, f"⛔ Лимит карты «{self.games.card_name(card_id)}»: {limit}.")
                edit_message(chat_id, message_id,
                             f"В колоде уже максимум копий «{self.games.card_name(card_id)}»: {limit}. "
                             f"Выберите другую карту ({len(deck)}/15).",
                             deck_add_keyboard(coll, deck))
                return
            deck.append(card_id)
            user['deck'] = deck
            self.store.persist()
            send_message(chat_id, f"➕ Добавлено: {self.games.card_name(card_id)} ({len(deck)}/15)")
            edit_message(chat_id, message_id,
                         f"Добавлено: {self.games.card_name(card_id)} ({len(deck)}/15). "
                         f"Можно добавить ещё или «↩️ Назад».",
                         deck_add_keyboard(coll, deck))
            return
        if action.startswith("delcard:"):
            idx = int(action.split(":")[1])
            if 0 <= idx < len(deck):
                removed = deck.pop(idx)
                user['deck'] = deck
                self.store.persist()
                send_message(chat_id, f"➖ Убрано: {self.games.card_name(removed)} ({len(deck)}/15)")
            if deck:
                edit_message(chat_id, message_id,
                             f"Убрано. Колода: {len(deck)}/15. Можно убрать ещё или «↩️ Назад».",
                             deck_remove_keyboard(deck))
            else:
                send_message(chat_id, "Колода пуста.")
                edit_message(chat_id, message_id, deck_screen_text(deck), deck_main_keyboard())
            return

    def save_deck(self, chat_id, message_id, user, deck):
        available = set(self.games.available_card_ids(user))
        for cid, count in Counter(deck).items():
            if cid not in self.games.cards or cid not in available or count > copy_limit(cid):
                edit_message(chat_id, message_id,
                             "⛔ В колоде есть недоступные карты или превышен лимит копий.",
                             deck_main_keyboard())
                return
        collection_total = user.get('collection', {})
        own_cards = sum(collection_total.values())
        if len(deck) == 15:
            user['deck'] = deck
            self.store.persist()
            edit_message(chat_id, message_id, "✅ Колода сохранена (15 карт).", [back_to_menu_button()])
            return
        if len(deck) < 15 and own_cards < 15:
            user['deck'] = deck
            self.store.persist()
            edit_message(chat_id, message_id,
                         f"✅ Колода сохранена ({len(deck)}/15). В матче бот доберёт недостающие карты до 15.",
                         [back_to_menu_button()])
            return
        edit_message(chat_id, message_id,
                     f"⛔ Нужно ровно 15 карт, сейчас {len(deck)}. "
                     f"У вас в коллекции более 15 карт — добавьте недостающие.",
                     deck_main_keyboard())
