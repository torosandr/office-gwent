import json
from config import FILES, BASE_CARD_IDS, SHOP_PRICES, LEGENDARY_CARD_IDS
from storage import load, save

class GameData:
    """
    Каталоги игры: карты, наборы и промокоды.
    Начисления карт и наборов, погашение промокодов.
    """
    def __init__(self):
        self.cards = load("cards")          # {id: {name, type, attack, health}}
        self.sets = load("sets")            # {id: {name, cards: [card_id]}}
        self.codes = load("codes")          # {code: {type, target, limit, used_by}}

    def reload(self):
        """Перечитывает каталоги карт/наборов/кодов с диска (для ручных правок)."""
        self.cards = load("cards")
        self.sets = load("sets")
        self.codes = load("codes")

    # ---------- Каталоги ----------
    def card_name(self, card_id):
        card = self.cards.get(card_id)
        return card["name"] if card else card_id

    def set_name(self, set_id):
        s = self.sets.get(set_id)
        return s["name"] if s else set_id

    # ---------- Начисление ----------
    def grant_card(self, user, card_id, count=1):
        if card_id not in self.cards:
            return False
        user.setdefault('collection', {})
        user['collection'][card_id] = user['collection'].get(card_id, 0) + count
        return True

    def grant_set(self, user, set_id):
        if set_id not in self.sets:
            return False
        for card_id in self.sets[set_id]['cards']:
            self.grant_card(user, card_id, 1)
        if set_id not in user.get('sets', []):
            user.setdefault('sets', []).append(set_id)
        return True

    def collection_ids(self, user):
        """Отсортированный список id карт, которые есть в коллекции пользователя (по названию)."""
        return sorted(user.get('collection', {}).keys(),
                      key=lambda c: self.cards.get(c, {}).get('name', c))

    def available_card_ids(self, user):
        """Все карты, доступные игроку: базовые + из его коллекции (юник, по названию)."""
        ids = set(BASE_CARD_IDS) | set(user.get('collection', {}).keys())
        return sorted(ids, key=lambda c: self.cards.get(c, {}).get('name', c))

    # ---------- Промокоды ----------
    def redeem_promo(self, user, code, user_store):
        """
        Погашает промокод. Возвращает (ok, message).
        Один промокод — до `limit` уникальных игроков; один игрок применит его лишь раз.
        """
        code = (code or "").strip()
        if code == "":
            return True, "Вы пропустили ввод промокода."

        if getattr(self, 'promo_service', None) is not None:
            from web_service import WebError
            try:
                result = self.promo_service.redeem_promo(user_store.id_of(user), code, immediate=True)
            except WebError as error:
                return False, str(error)
            user['collection'] = result['collection']
            user['sets'] = result['sets']
            user_store.persist()
            return True, f"✅ Промокод принят! Начислен набор: {result['name']}\nОсталось применений: {result['remaining']}"

        # ищем промокод без учёта регистра
        key = None
        for existing in self.codes:
            if existing.upper() == code.upper():
                key = existing
                break
        if key is None:
            return False, "❌ Неверный промокод."
        promo = self.codes[key]

        uid = user_store.id_of(user)
        limit = promo.get('limit', 1)
        used_by = promo.get('used_by', [])
        if len(used_by) >= limit:
            return False, f"❌ Этот промокод уже использован (лимит {limit} игроков исчерпан)."
        if any(u.get('id') == uid for u in used_by):
            return False, "❌ Вы уже использовали этот промокод ранее."

        target = promo.get('target')
        entry = {"id": uid, "nickname": user.get('nickname', "?")}

        if promo.get('type') == 'set':
            if not self.grant_set(user, target):
                return False, "❌ Внутренняя ошибка: набор не найден."
            promo['used_by'] = used_by + [entry]
            user_store.persist()
            save("codes", self.codes)
            remaining = limit - len(promo['used_by'])
            return True, f"✅ Промокод принят! Начислен набор: {self.set_name(target)}\nОсталось применений: {remaining}"

        if promo.get('type') == 'card':
            if not self.grant_card(user, target, 1):
                return False, "❌ Внутренняя ошибка: карта не найдена."
            promo['used_by'] = used_by + [entry]
            user_store.persist()
            save("codes", self.codes)
            remaining = limit - len(promo['used_by'])
            return True, f"✅ Промокод принят! Начислена карта: {self.card_name(target)}\nОсталось применений: {remaining}"

        return False, "❌ Неверный тип промокода."

    # ---------- Вывод для пользователя ----------
    def describe_card(self, card_id):
        card = self.cards.get(card_id, {})
        if card.get('type') == 'spell':
            return f"✨ {card['name']} (заклинание)"
        return f"⚔️ {card['name']} ({card['attack']}/{card['health']})"

    def full_card_text(self, card_id):
        """Полное описание карты для просмотра."""
        card = self.cards.get(card_id)
        if not card:
            return "Карта не найдена."
        legendary = card_id in LEGENDARY_CARD_IDS
        name_html = (f"<b><i>{card['name']}</i></b>" if legendary else f"<b>{card['name']}</b>")
        lines = []
        if card.get('type') == 'creature':
            lines.append(f"⚔️ {name_html} — Существо")
            lines.append(f"Атака: {card['attack']} | Здоровье: {card['health']} | Стоимость: {card.get('cost', 0)} ☕")
        else:
            lines.append(f"✨ {name_html} — Заклинание")
            lines.append(f"Стоимость: {card.get('cost', 0)} ☕")
        if legendary:
            lines.append("⭐ <b><i>Легендарная</i></b>")
        if card.get('status'):
            status_names = {
                'таунт': '🛡 Таунт',
                'супер_таунт': '⛔ Супер-таунт',
                'кофе': '☕ Кофе',
                'дедлайн': '💣 Дедлайн',
                'усыпить': '💤 Усыпление',
                'урон': '🔫 Урон',
                'хил_цель': '💚 Лечение (цель)',
                'урон_цель': '🎯 Урон (цель)',
                'рандом': '🎲 Случайный эффект',
                'аура': '🌀 Аура',
                'покур': '💨 Покур',
                'няня': '💗 Няня',
                'сокращение': '🔪 Сокращение',
                'хил_прямой': '💚 Лечение',
                'эспрессо': '☕ Эспрессо',
                'просрочка': '🕰 Просрочка',
                'гречка': '🍚 Гречка',
                'заморозка': '🧊 Заморозка',
                'супер_таунт': '⛔ Супер-таунт',
                'лень': '🦥 Лень',
                'пиво': '🍺 Пиво',
                'предвкушение': '🍻 Предвкушение',
                'кофе_цапля': '🍃',
            }
            if k := status_names.get(card['status']):
                lines.append(f"Статус: {k}")
        if card.get('desc'):
            lines.append(f"\n📜 {card['desc']}")
        return "\n".join(lines)

    def card_id_list(self, user=None):
        """Список id карт: все (если user=None) или только из коллекции."""
        if user is None:
            return sorted(self.cards.keys(), key=lambda c: self.cards[c].get('name', c))
        own = set(user.get('collection', {}).keys())
        return sorted(own, key=lambda c: self.cards[c].get('name', c))

    def collection_text(self, user):
        if not user.get('collection'):
            return "У вас пока нет карт. Откройте набор или введите промокод!"
        lines = []
        for card_id, count in sorted(user['collection'].items()):
            copies = f" ×{count}" if count > 1 else ""
            lines.append(f"{self.describe_card(card_id)}{copies}")
        return "\n".join(lines)

    # ---------- Магазин ----------

    def shop_items(self):
        """Список карт в магазине с ценами: (card_id, name, price, legendary)."""
        items = []
        for card_id, price in SHOP_PRICES.items():
            card = self.cards.get(card_id)
            if not card:
                continue
            legendary = card_id in LEGENDARY_CARD_IDS
            items.append((card_id, card['name'], price, legendary))
        return items

    def can_buy(self, user, card_id):
        """
        Проверка покупки карты. Возвращает (ok, сообщение).
        Лимиты: обычная карта — не больше 2 копий, легендарная — не больше 1.
        """
        card = self.cards.get(card_id)
        if not card:
            return False, "Внутренняя ошибка: карта не найдена."
        price = SHOP_PRICES.get(card_id)
        if price is None:
            return False, "Эта карта не продаётся в магазине."
        coins = user.get('coins', 0)
        if coins < price:
            return False, f"Не хватает монет (нужно {price}, у вас {coins})."
        have = user.get('collection', {}).get(card_id, 0)
        if card_id in LEGENDARY_CARD_IDS:
            if have >= 1:
                return False, "Легендарную карту можно купить только 1 раз."
        else:
            if have >= 2:
                return False, "Обычной карты нельзя иметь больше 2 копий."
        return True, ""

    def buy_card(self, user, card_id):
        """Покупает карту. Возвращает (ok, сообщение)."""
        ok, err = self.can_buy(user, card_id)
        if not ok:
            return False, err
        price = SHOP_PRICES[card_id]
        user['coins'] = user.get('coins', 0) - price
        self.grant_card(user, card_id, 1)
        return True, f"✅ Куплено: {self.card_name(card_id)} (осталось монет: {user['coins']})"