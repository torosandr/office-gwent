import random
from cards import get as card_info, CARDS, copy_limit

class Player:
    """Игрок: ресурсы, рука, стол, колода."""

    def __init__(self, name, game, hero_id=None):
        self.name = name
        self._game = game
        self.hero_id = hero_id
        self.coffee = game.START_COFFEE
        self.stress = game.MAX_STRESS
        self.hand = []         # list[card_id]
        self.board = []        # list[Unit]
        self.deck = None       # list[card_id]
        self.hero_used = False
        self.skip_actions = False  # текущий ход без действий (Покур активен)
        self.skip_pending = False  # следующий ход пропускается (Покур сыгран)
        self.pending = []  # отложенные эффекты: {turns, type, amount}

    # --- колода ---

    def build_deck(self, card_ids, deck_size, rng):
        """Собирает колоду.
        card_ids — выбранные игроком карты. Если меньше deck_size — добирает
        случайными картами: обычные до 2 копий, легендарные до 1."""
        used = {}
        deck = []
        for cid in card_ids:
            if cid in CARDS and used.get(cid, 0) < copy_limit(cid):
                deck.append(cid)
                used[cid] = used.get(cid, 0) + 1
        # добираем до нужного размера случайными картами
        if len(deck) < deck_size:
            pool = list(CARDS.keys())
            # случайный добор, честно разрешая до 2 копий
            max_tries = deck_size * 30
            while len(deck) < deck_size and max_tries > 0:
                max_tries -= 1
                cand = rng.choice(pool)
                if used.get(cand, 0) < copy_limit(cand):
                    deck.append(cand)
                    used[cand] = used.get(cand, 0) + 1
        rng.shuffle(deck)
        self.deck = deck[:deck_size]
        # база для перетасовки (гибрид: 1 полный повтор, потом усталость)
        self._base_deck = list(self.deck)
        self.refills = 0          # сколько раз уже тасовали заново
        self.fatigue_damage = 0   # текущий урон усталости

    def draw(self):
        """Берёт карту. Возвращает ('card', card_id) или ('fatigue', урон).
        Колода перетасовывается заново один раз, потом идёт усталость."""
        if self.deck:
            return 'card', self.deck.pop()
        if self.refills == 0:
            # перетасовываем базу заново один раз
            import random
            random.shuffle(self._base_deck)
            self.deck = list(self._base_deck)
            self.refills = 1
            return 'card', self.deck.pop()
        # колода исчерпана повторно — усталость
        self.fatigue_damage += 1
        return 'fatigue', self.fatigue_damage

    # --- атака существ ---

    def can_afford(self, card_id):
        return self.coffee >= card_info(card_id).get('cost', 0)
