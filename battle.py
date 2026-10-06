import random
from cards import CARDS, get as card_info, BattleError
from unit import Unit
from player import Player

# Реэкспорт для внешних модулей (handlers, ui, тесты)
__all__ = ["Game", "BattleError", "CARDS"]


class Game:
    """
    Движок боя «Офисный Гвинт» (нокаут из Hearthstone).

    Игроки: self.players = {1: Player, 2: Player}. Ход по очереди.
    Формат: нокаут — довести стресс соперника до 0.
    """
    HERO_COST = 2
    HERO_HEAL = 3
    MAX_STRESS = 20
    START_COFFEE = 3
    MAX_COFFEE = 10
    START_HAND = 4
    DECK_SIZE = 15
    LOG_LIMIT = 100

    def __init__(self, p1_name, p2_name, seed=None, deck1=None, deck2=None, hero1=None, hero2=None):
        self.rng = random.Random(seed)
        self.players = {
            1: Player(p1_name, self, hero1),
            2: Player(p2_name, self, hero2),
        }
        self.turn = self.rng.choice([1, 2])
        self.phase = 'active'
        self.winner = None
        self.winner_name = None
        self.started = False
        self.log = []
        self.turn_count = 0  # счётчик «полных циклов» (твой ход + ход соперника)

        # используем сохранённые колоды игроков (могут быть пустыми/меньше 15),
        # недостающее добираем случайными картами
        base_keys = list(CARDS.keys())
        self.players[1].build_deck(deck1 if deck1 is not None else base_keys,
                                   self.DECK_SIZE, self.rng)
        self.players[2].build_deck(deck2 if deck2 is not None else base_keys,
                                   self.DECK_SIZE, self.rng)

    # ---------- вспомогательное ----------

    def _log(self, msg):
        self.log.append(msg)
        if len(self.log) > self.LOG_LIMIT:
            del self.log[:-self.LOG_LIMIT]

    def _name(self, pnum):
        return self.players[pnum].name

    def _opp(self, pnum):
        return 3 - pnum

    def _cost(self, card_id):
        return card_info(card_id).get('cost', 0)

    def _action_error(self, pnum):
        if self.phase != 'active':
            return 'Партия уже завершена.'
        if self.turn != pnum:
            return 'Сейчас не ваш ход.'
        if self.players[pnum].skip_actions:
            return 'Вы пропускаете этот ход (Покур) — действия запрещены.'
        return ''

    # ---------- старт ----------

    def _draw_for(self, pnum):
        """Добор карты с обработкой усталости (наносит растущий урон герою)."""
        p = self.players[pnum]
        kind, val = p.draw()
        if kind == 'card':
            p.hand.append(val)
        else:  # усталость
            self._damage_hero(pnum, val)
            self._log(f"🔥 {self._name(pnum)} страдает от усталости: −{val} стресса")
            self._check_win()

    def start(self):
        for pnum in (1, 2):
            for _ in range(self.START_HAND):
                self._draw_for(pnum)
        self.started = True
        return self._name(self.turn) + ' начинает.'

    # ---------- ход ----------

    def begin_turn(self, pnum):
        if self.phase != 'active':
            return
        p = self.players[pnum]
        p.coffee = min(p.coffee + 1, self.MAX_COFFEE)
        self._draw_for(pnum)
        if self.phase == 'finished':
            return
        for u in p.board:
            u.asleep = False
            u.attacked = False
        p.hero_used = False
        # Покур: если отложен пропуск — активируем запрет действий на этот ход
        if getattr(p, 'skip_pending', False):
            p.skip_pending = False
            p.skip_actions = True
            self._log(f"💤 {self._name(pnum)} пропускает ход из-за Покура")
        self._tick_deadlines(p)
        if self.phase == 'finished':
            return
        # аура (посудомойка) тикает 1 раз за полный цикл (твой ход + ход соперника)
        self.turn_count += 1
        if self.turn_count % 2 == 1:
            self._tick_auras()
            if self.phase == 'finished':
                return
            self._tick_freeze()
        self._tick_nyanya(p)
        self._tick_growth(p)
        self._tick_predvkushenie(p)
        self._tick_pending(pnum)

    def end_turn(self):
        if self.phase != 'active':
            raise BattleError('Партия уже завершена.')
        c = self.players[self.turn]
        for u in list(c.board):
            if u.status == 'реген':
                u.heal(1)
            elif u.status == 'кофе':
                c.coffee = min(c.coffee + 1, self.MAX_COFFEE)
        # эфемерные существа (маркетолог): проживают один полный ход и уходят в конце
        for u in list(c.board):
            if u.status == 'эфемерный':
                u.linger -= 1
                if u.linger <= 0:
                    c.board.remove(u)
                    self._log(f"💨 {u.name} уходит с поля (его время вышло)")
        for u in c.board:
            u.stunned = False
        c.skip_actions = False  # запрет действий действовал только этот ход
        self._log(f"🔁 Конец хода {self._name(self.turn)}")
        self.turn = self._opp(self.turn)
        self.begin_turn(self.turn)

    def _tick_deadlines(self, p):
        for u in list(p.board):
            if u.status == 'дедлайн' and not u.stunned:
                u.timer = (u.timer or 1) - 1
                if u.timer <= 0:
                    opp = self._opp(self.turn)
                    self._damage_hero(opp, 8)
                    self._log(f"💣 {self._name(self.turn)}: Дедлайн взрывается! 8 урона {self._name(opp)}")
                    p.board.remove(u)
                    if self._check_win():
                        return

    def _tick_auras(self):
        """Пассивные ауры (посудомойка): каждая аура каждый ход наносит 1 урон всем существам + 1 герою соперника их владельца."""
        # собираем все живые ауры с обеих сторон, чтобы каждая наносила урон отдельно
        all_auras = []
        for owner_pnum in (1, 2):
            for u in self.players[owner_pnum].board:
                if u.is_aura():
                    all_auras.append((owner_pnum, u))
        for owner_pnum, _aura in all_auras:
            self._damage_hero(self._opp(owner_pnum), 1)
            self._log(f"🌀 {self._name(owner_pnum)}: Посудомойка наносит 1 урон герою {self._name(self._opp(owner_pnum))}")
            for pnum in (1, 2):
                for u in list(self.players[pnum].board):
                    if not u.is_aura():
                        u.take_damage(1)
                        if not u.is_alive():
                            self._log(f"💀 {u.name} погибает от Посудомойки")
                            self.players[pnum].board.remove(u)
            if self._check_win():
                return

    def _tick_pending(self, pnum):
        """Отсчитывает отложенные эффекты владельца (через N его ходов)."""
        p = self.players[pnum]
        remaining = []
        for index, item in enumerate(p.pending):
            item['turns'] -= 1
            if item['turns'] <= 0:
                self._resolve_pending(pnum, item)
                if self.phase == 'finished':
                    p.pending = remaining + p.pending[index + 1:]
                    return
            else:
                remaining.append(item)
        p.pending = remaining

    def _resolve_pending(self, pnum, item):
        t = item['type']
        amt = item['amount']
        unit = item.get('unit')
        if t == 'heal_hero':
            self._heal_hero(pnum, amt)
            self._log(f"💚 {self._name(pnum)}: сработал отложенный эффект +{amt} стресса")
            if unit is not None and unit in self.players[pnum].board:
                self.players[pnum].board.remove(unit)
                self._log(f"🍚 {unit.name} уходит с поля (эффект исполнен)")
        elif t == 'damage_hero':
            self._damage_hero(pnum, amt)
            self._log(f"💥 {self._name(pnum)}: сработал отложенный эффект −{amt} стресса")
            self._check_win()
        elif t == 'coffee':
            self.players[pnum].coffee = min(self.players[pnum].coffee + amt, self.MAX_COFFEE)
            self._log(f"☕ {self._name(pnum)}: Эспрессо даёт +{amt} кофе")
        elif t == 'remove_unit':
            if unit is not None and unit in self.players[pnum].board:
                self.players[pnum].board.remove(unit)
                self._log(f"💨 {unit.name} уходит с поля (время маркетолога вышло)")

    def _tick_freeze(self):
        """Считает заморозку: каждый полный цикл уменьшает freeze_cycles у всех существ."""
        for pnum_i in (1, 2):
            for u in self.players[pnum_i].board:
                if u.freeze_cycles > 0:
                    u.freeze_cycles -= 1
                    if u.freeze_cycles <= 0 and u.is_alive():
                        pass  # разморозилось

    def _tick_growth(self, p):
        """Завал: в начале хода владельца здоровье растёт на 1 (и максимум)."""
        for u in p.board:
            if u.growth and u.is_alive():
                u.max_hp += 1
                u.hp += 1
                self._log(f"⛰ {self._name(self.turn)}: Завал растёт — здоровье {u.hp}")

    def _tick_predvkushenie(self, p):
        """Предвкушение: в начале хода игрока лечит героя на 1."""
        if not any(u.status == 'предвкушение' and u.is_alive() for u in p.board):
            return
        self._heal_hero(self.turn, 1)
        self._log(f"🍻 {self._name(self.turn)}: Предвкушение восстанавливает 1 стресс")

    def _tick_nyanya(self, p):
        """Нянячка Таня: в начале хода лечит 1 хп своим существам.
        Обычные — до максимума, существа без потолка (Степан) — неограниченно."""
        if not any(u.status == 'няня' and u.is_alive() for u in p.board):
            return
        healed = 0
        for u in p.board:
            if u.is_alive() and (u.unlimited_heal or u.hp < u.max_hp):
                u.heal(1)
                healed += 1
        if healed:
            self._log(f"💗 {self._name(self.turn)}: Нянячка Таня лечит {healed} существ на 1 хп")

    # ---------- розыгрыш карт ----------

    def can_play(self, pnum, hand_idx):
        err = self._action_error(pnum)
        if err:
            return False, err
        p = self.players[pnum]
        if not (0 <= hand_idx < len(p.hand)):
            return False, 'Нет такой карты в руке.'
        card_id = p.hand[hand_idx]
        if p.coffee < self._cost(card_id):
            return False, 'Не хватает кофе.'
        return True, ''

    def play_card(self, pnum, hand_idx):
        ok, err = self.can_play(pnum, hand_idx)
        if not ok:
            raise BattleError(err)
        p = self.players[pnum]
        card_id = p.hand[hand_idx]
        if self.is_targeted(card_id):
            raise BattleError('Выберите цель заклинания.')
        p.hand.pop(hand_idx)
        p.coffee -= self._cost(card_id)
        info = card_info(card_id)

        if info.get('type') == 'creature':
            unit = Unit(card_id)
            p.board.append(unit)
            self._log(f"☕ {self._name(pnum)} сыграл существо: {info['name']}")
            # пассивный герой (Мария Рыбина): +1 атаки и +1 макс. здоровья
            self._apply_hero_passive(pnum, unit)
            # Зелёная гречка: через 2 хода владельца лечит героя на 10 и удаляется
            if info.get('status') == 'гречка':
                p.pending.append({'turns': 2, 'type': 'heal_hero', 'amount': 10, 'unit': unit})
            # Маркетолог (эфемерный) обрабатывается в end_turn владельца через unit.linger
        else:
            self._play_spell(pnum, card_id, info, None)
            self._log(f"✨ {self._name(pnum)} сыграл заклинание: {info['name']}")
        self._check_win()
        return f"Сыграно: {info['name']}"

    def is_targeted(self, card_id):
        """Заклинание требует выбора цели ('урон_цель'/'хил_цель'/'кража')."""
        info = card_info(card_id)
        return info.get('type') == 'spell' and info.get('status') in ('урон_цель', 'хил_цель', 'кража', 'сокращение')

    def cast_targeted_spell(self, pnum, hand_idx, target):
        """Разыгрывает целевое заклинание с указанной целью.
        target: 'hero_self' | 'hero_opp' | индекс существа (свой или чужой)."""
        ok, err = self.can_play(pnum, hand_idx)
        if not ok:
            raise BattleError(err)
        p = self.players[pnum]
        card_id = p.hand[hand_idx]
        info = card_info(card_id)
        if not self.is_targeted(card_id):
            raise BattleError('Эта карта не требует цели.')
        self._validate_spell_target(pnum, info['status'], target)
        p.hand.pop(hand_idx)
        p.coffee -= info.get('cost', 0)
        self._play_spell(pnum, card_id, info, target)
        self._log(f"✨ {self._name(pnum)} сыграл заклинание: {info['name']}")
        self._check_win()
        return f"Сыграно: {info['name']}"

    def _validate_spell_target(self, pnum, status, target):
        if status == 'урон_цель' and target == 'hero_opp':
            return
        if status == 'хил_цель' and target == 'hero_self':
            return
        side = self._opp(pnum) if status in ('урон_цель', 'кража') else pnum
        player = self.players[side]
        idx = self._resolve_target_uindex(player, target)
        unit = player.board[idx]
        if status == 'сокращение' and (unit.is_super_taunt() or unit.card == 'проджект_менеджер'):
            raise BattleError('Нельзя сократить Проджект Менеджера.')

    def _play_spell(self, pnum, card_id, info, target):
        opp = self._opp(pnum)
        status = info.get('status')
        power = info.get('power', info.get('attack', 0))
        if status == 'усыпить':
            for u in self.players[opp].board:
                u.stunned = True
        elif status == 'урон':
            self._damage_hero(opp, power)
        elif status == 'кофе':
            self.players[pnum].coffee = min(self.players[pnum].coffee + 2, self.MAX_COFFEE)
        elif status == 'урон_цель':
            self._resolve_offensive(target, pnum, self.players[opp], power, info['name'])
        elif status == 'хил_цель':
            self._resolve_heal(target, pnum, power, info['name'])
        elif status == 'покур':
            self._heal_hero(pnum, power)
            self.players[pnum].skip_pending = True
            self._log(f"💆 {self._name(pnum)}: {info['name']} лечит героя на {power}, следующий ход без действий")
        elif status == 'кража':
            self._resolve_steal(target, pnum, self.players[opp], info['name'])
        elif status == 'рандом':
            self._resolve_random(pnum, opp, info['name'])
        elif status == 'хил_прямой':
            self._heal_hero(pnum, power)
            self._log(f"💚 {self._name(pnum)}: {info['name']} восстанавливает {power} стресса")
        elif status == 'эспрессо':
            self.players[pnum].pending.append({'turns': 1, 'type': 'coffee', 'amount': power})
            self._log(f"☕ {self._name(pnum)}: {info['name']} даст +{power} кофе в следующий ход")
        elif status == 'просрочка':
            self._heal_hero(pnum, power)
            self.players[pnum].pending.append({'turns': 2, 'type': 'damage_hero', 'amount': power + 2})
            self._log(f"💚 {self._name(pnum)}: {info['name']} +{power} стресса, но через 2 хода −{power + 2}")
        elif status == 'сокращение':
            self._resolve_coke(target, pnum, power, info['name'])
        elif status == 'лень':
            self._damage_hero(pnum, power * 2)  # −4 стресса
            self.players[pnum].coffee = min(self.players[pnum].coffee + power, self.MAX_COFFEE)
            self._log(f"🦥 {self._name(pnum)}: {info['name']} −{power*2} стресса, +{power} кофе")
        elif status == 'пиво':
            self._heal_hero(pnum, power)
            self._log(f"🍺 {self._name(pnum)}: {info['name']} восстанавливает {power} стресса")
        elif status == 'заморозка':
            for pnum_i in (1, 2):
                for u in self.players[pnum_i].board:
                    u.freeze_cycles = max(u.freeze_cycles, power)
            self._log(f"🧊 {self._name(pnum)}: {info['name']} замораживает ВСЕХ существ на {power} цикла")

    def _resolve_offensive(self, target, pnum, opp, power, spell_name):
        if target == 'hero_opp':
            dmg = min(opp.stress, power)
            opp.stress = max(0, opp.stress - power)
            self._log(f"🎯 {self._name(pnum)}: {spell_name} бьёт героя на {dmg}")
            self._check_win_opp(opp)
        else:
            idx = self._resolve_target_uindex(opp, target)
            unit = opp.board[idx]
            self._damage_unit(unit, power)
            self._log(f"🎯 {self._name(pnum)}: {spell_name} бьёт {unit.name} на {power}")
            if not unit.is_alive():
                self._log(f"💀 {unit.name} погибает")
                opp.board.remove(unit)

    def _check_win_opp(self, opp_player):
        """Проверка победы при уроне герою от заклинания."""
        self._check_win()

    def _resolve_heal(self, target, pnum, power, spell_name):
        if target == 'hero_self':
            self._heal_hero(pnum, power)
            self._log(f"💚 {self._name(pnum)}: {spell_name} лечит героя на {power}")
        else:
            idx = self._resolve_target_uindex(self.players[pnum], target)
            unit = self.players[pnum].board[idx]
            unit.heal(power)
            self._log(f"💚 {self._name(pnum)}: {spell_name} лечит {unit.name} на {power}")

    def _resolve_coke(self, target, pnum, power, spell_name):
        """Сокращение: уничтожает своё существо → +power стресса герою и +power кофе."""
        if target in ('hero_self', 'hero_opp'):
            raise BattleError('Выберите существо, которое хотите уничтожить (не героя).')
        p = self.players[pnum]
        idx = self._resolve_target_uindex(p, target)
        victim = p.board[idx]
        if victim.is_super_taunt() or victim.card == 'проджект_менеджер':
            raise BattleError('Нельзя сократить Проджект Менеджера.')
        p.board.remove(victim)
        self._heal_hero(pnum, power)
        p.coffee = min(p.coffee + power, self.MAX_COFFEE)
        self._log(f"🔪 {self._name(pnum)}: {spell_name} уничтожает {victim.name} → +{power} стресса, +{power} кофе")

    def _resolve_steal(self, target, pnum, opp_player, spell_name):
        """Капучино: забирает вражеское существо в свою команду."""
        if target == 'hero_opp':
            raise BattleError('Нельзя забрать героя — выберите существо.')
        idx = self._resolve_target_uindex(opp_player, target)
        unit = opp_player.board[idx]
        opp_player.board.remove(unit)
        self.players[pnum].board.append(unit)
        # бонус пассивного героя нового владельца
        self._apply_hero_passive(pnum, unit)
        # существо просыпается и его можно использовать как своё
        unit.asleep = True  # сыграно в этот ход — обычное правило сонной болезни
        unit.attacked = False
        unit.stunned = False
        self._log(f"☕ {self._name(pnum)}: {spell_name} забирает {unit.name} из команды соперника")

    def _resolve_random(self, pnum, opp, spell_name):
        """Панини с вишней: случайный эффект из 5 вариантов, применяется к случайной цели (себе или сопернику)."""
        who = self.rng.choice(['self', 'opp'])  # цель: себя или соперник
        r = self.rng.choice(['damage', 'heal', 'coffee', 'sleep', 'drain'])
        side = 'себе' if who == 'self' else 'сопернику'
        victim_num = pnum if who == 'self' else opp
        if r == 'damage':
            self._damage_hero(victim_num, 4)
            self._log(f"🎲 {self._name(pnum)}: {spell_name} наносит 4 урона герою {side}")
        elif r == 'heal':
            self._heal_hero(victim_num, 4)
            self._log(f"🎲 {self._name(pnum)}: {spell_name} лечит героя {side} на 4")
        elif r == 'coffee':
            self.players[victim_num].coffee = min(self.players[victim_num].coffee + 3, self.MAX_COFFEE)
            self._log(f"🎲 {self._name(pnum)}: {spell_name} даёт +3 кофе {side}")
        elif r == 'sleep':
            alive = [u for u in self.players[victim_num].board if u.is_alive()]
            if alive:
                victim = self.rng.choice(alive)
                victim.stunned = True
                self._log(f"🎲 {self._name(pnum)}: {spell_name} усыпляет существо {victim.name} у {side}")
            else:
                self._log(f"🎲 {self._name(pnum)}: {spell_name} — некого усыплять, эффект пропадает")
        elif r == 'drain':
            self.players[victim_num].coffee = 0
            self._log(f"🎲 {self._name(pnum)}: {spell_name} обнуляет кофе {side}")

    # ---------- атака ----------

    def can_attack(self, pnum, board_idx, target):
        err = self._action_error(pnum)
        if err:
            raise BattleError(err)
        p = self.players[pnum]
        if not (0 <= board_idx < len(p.board)):
            raise BattleError('Нет такого существа.')
        u = p.board[board_idx]
        if u.asleep or u.stunned or u.freeze_cycles > 0:
            raise BattleError('Существо уже действовало в этот ход или спит.')
        if u.attacked:
            raise BattleError('Существо уже атаковало в этот ход.')
        if not u.is_alive():
            raise BattleError('Существо мертво.')
        if u.attack <= 0:
            raise BattleError('Это существо не может атаковать (атака 0).')
        if target == 'hero':
            opp_board = self.players[self._opp(pnum)].board
            if any(x.is_blocker() for x in opp_board if x.is_alive()):
                raise BattleError('На пути стоит существо с таунтом.')
        else:
            # Цель — существо соперника. Супер-таунт блокирует атаки по другим существам.
            opp = self.players[self._opp(pnum)]
            idx = self._resolve_target_uindex(opp, target)
            defender = opp.board[idx]
            super_taunts = [x for x in opp.board if x.is_super_taunt() and x.is_alive()]
            if super_taunts and not defender.is_super_taunt():
                raise BattleError('Проджект Менеджер блокирует атаки по другим существам.')
        return True

    def attack(self, pnum, board_idx, target):
        self.can_attack(pnum, board_idx, target)
        p = self.players[pnum]
        opp = self.players[self._opp(pnum)]
        u = p.board[board_idx]

        if target == 'hero':
            dmg = self._damage_hero(self._opp(pnum), u.attack)
            self._lifesteal(pnum, u, dmg)
            self._log(f"⚔️ {self._name(pnum)}: {u.name} бьёт героя на {u.attack}")
        else:
            target_idx = self._resolve_target_uindex(opp, target)
            defender = opp.board[target_idx]
            # посудомойка (аура): атака обоюдно уничтожает обоих — обмен без учёта хп
            if defender.is_aura():
                p.board.remove(u)
                opp.board.remove(defender)
                self._log(f"⚔️ {self._name(pnum)}: {u.name} и {defender.name} уничтожают друг друга")
                self._check_win()
                u.attacked = True
                return
            self._lifesteal(pnum, u, defender.attack)
            self._damage_unit(u, defender.attack)
            self._damage_unit(defender, u.attack)
            self._log(f"⚔️ {self._name(pnum)}: {u.name} атакует {defender.name}, урон {u.attack}↔{defender.attack}")
            if u.hp <= 0:
                self._log(f"💀 {u.name} погибает")
                p.board.remove(u)
            if defender.hp <= 0:
                self._log(f"💀 {defender.name} погибает")
                opp.board.remove(defender)

        u.attacked = True
        self._check_win()

    def _resolve_target_uindex(self, opp, target):
        try:
            idx = int(target)
        except (TypeError, ValueError):
            raise BattleError('Некорректная цель атаки.')
        if 0 <= idx < len(opp.board) and opp.board[idx].is_alive():
            return idx
        raise BattleError('Некорректная цель атаки.')

    def _damage_unit(self, unit, amount):
        unit.take_damage(amount)

    def _lifesteal(self, pnum, unit, amount):
        if unit.status == 'вампиризм':
            self._heal_hero(pnum, amount)

    def _damage_hero(self, pnum, amount):
        p = self.players[pnum]
        dmg = min(p.stress, amount)
        p.stress = max(0, p.stress - amount)
        return dmg

    def _heal_hero(self, pnum, amount):
        p = self.players[pnum]
        before = p.stress
        p.stress = min(p.stress + amount, self.MAX_STRESS)
        self._healed_total = getattr(self, "_healed_total", 0) + max(0, p.stress - before)

    # ---------- герой ----------

    def can_use_hero(self, pnum):
        err = self._action_error(pnum)
        if err:
            return False, err
        p = self.players[pnum]
        if not self.hero_has_active(pnum):
            return False, 'У этого героя нет активной способности.'
        if p.hero_used:
            return False, 'Способность героя уже использована в этот ход.'
        info = self._hero_info(pnum)
        cost = info.get('active_cost', 0)
        if p.coffee < cost:
            return False, 'Не хватает кофе на способность.'
        return True, ''

    def use_hero(self, pnum):
        ok, err = self.can_use_hero(pnum)
        if not ok:
            raise BattleError(err)
        p = self.players[pnum]
        info = self._hero_info(pnum)
        cost = info.get('active_cost', 0)
        amount = info.get('active_amount', 0)
        p.coffee -= cost
        self._heal_hero(pnum, amount)
        p.hero_used = True
        self._log(f"💆 {self._name(pnum)} использует способность героя: −{cost}☕, +{amount} стресса")
        return f'Герой лечит {amount} стресса.'

    # ---------- герой: справка ----------

    def _apply_hero_passive(self, pnum, unit):
        """Пассивный бонус героя при появлении существа на своей стороне."""
        info = self._hero_info(pnum)
        if info.get('type') != 'passive':
            return
        atk = info.get('passive_bonus_attack', 0)
        hp = info.get('passive_bonus_health', 0)
        if atk or hp:
            unit.attack += atk
            unit.max_hp += hp
            unit.hp += hp
            self._log(f"🌟 {self._name(pnum)}: {unit.name} усилен героем (+{atk} атк, +{hp} хп)")

    def _hero_info(self, pnum):
        from config import HEROES
        return HEROES.get(self.players[pnum].hero_id, {})

    def hero_name(self, pnum):
        return self._hero_info(pnum).get('name', 'Герой')

    def hero_is_passive(self, pnum):
        return self._hero_info(pnum).get('type') == 'passive'

    def hero_has_active(self, pnum):
        return self._hero_info(pnum).get('type') == 'active'

    # ---------- победа ----------

    def _check_win(self):
        if self.phase == 'finished':
            return True
        for pnum in (1, 2):
            if self.players[pnum].stress <= 0:
                self.phase = 'finished'
                self.winner = self._opp(pnum)
                self.winner_name = self.players[self.winner].name
                return True
        return False

    # ---------- отображение ----------

    def render(self):
        lines = []
        for pnum in (2, 1):
            p = self.players[pnum]
            marker = '➡️' if self.turn == pnum else '  '
            who = 'ВЫ' if pnum == 1 else 'СОПЕРНИК'
            lines.append(f"{marker} {who}: {p.name} | ☕{p.coffee} 😤{p.stress}")
            board = []
            for u in p.board:
                tag = '💤' if u.asleep else ''
                if u.status:
                    tag += f"[{u.status}]"
                if u.timer is not None:
                    tag += f"⏱{u.timer}"
                board.append(f"{u.name}({u.attack}/{u.hp}){tag}")
            lines.append('   стол: ' + (', '.join(board) if board else '—'))
        return '\n'.join(lines)
