from cards import get as card_info
import uuid

class Unit:
    """Существо на столе игрока."""

    def __init__(self, card_id):
        self._visual_id = uuid.uuid4().hex
        info = card_info(card_id)
        self.card = card_id
        self.name = info.get('name', card_id)
        self.attack = info.get('attack', 0)
        self.cost = info.get('cost', 0)
        self.max_hp = info.get('health', 1)
        self.hp = self.max_hp
        # срочно может ходить сразу в этот же ход, остальные «спят» до следующего
        self.asleep = info.get('status') != 'срочно'
        self.attacked = False
        self.stunned = False
        # статус существа (таунт, пенка, реген, вампиризм, дедлайн, кофе...)
        self.status = info.get('status')
        # таймер для дедлайн-бомбы
        self.timer = info.get('timer') if self.status == 'дедлайн' else None
        # аурные существа (посудомойка) нельзя убить обычным уроном — только жертвой
        self.indestructible = (self.status == 'аура')
        # «Степан»: у него нет потолка здоровья — хп можно лечить неограниченно
        self.unlimited_heal = (self.status == 'неограниченный')
        # заморозка (Заседание Женского Клуба): сколько полных циклов существо не может действовать
        self.freeze_cycles = 0
        # Завал: с каждым ходом владельца здоровье растёт на 1
        self.growth = bool(info.get('growth'))
        # эфемерное (маркетолог): живёт до конца СЛЕДУЮЩЕГО своего хода (успевает атаковать), потом уходит
        self.linger = 2 if self.status == 'эфемерный' else 0

    # --- состояние ---

    def is_alive(self):
        return self.hp > 0

    def can_act(self):
        """Может ли существо атаковать в этом ходе."""
        return (self.is_alive() and not self.asleep and not self.stunned
                and not self.attacked and self.freeze_cycles <= 0)

    def is_frozen(self):
        return self.freeze_cycles > 0

    def is_taunt(self):
        return self.status == 'таунт'

    def is_super_taunt(self):
        return self.status == 'супер_таунт'

    def is_blocker(self):
        """Блокирует атаки (таунт или супер-таунт)."""
        return self.status in ('таунт', 'супер_таунт')

    def is_aura(self):
        return self.status == 'аура'

    # --- урон ---

    def take_damage(self, amount):
        """Наносит урон. Учитывает пенку (поглощает первый удар). Возвращает реально нанесённый урон.
        Аурное существо (посудомойка) не может умереть от обычного урона — hp не опускается ниже 1."""
        if self.status == 'пенка':
            self.status = None  # щит снят
            self._blocked_total = getattr(self, '_blocked_total', 0) + 1
            return 0
        floor = 1 if self.indestructible else 0
        actual = min(amount, self.hp - floor)
        self.hp -= actual
        self._damaged_total = getattr(self, '_damaged_total', 0) + max(0, actual)
        return actual

    def heal(self, amount):
        before = self.hp
        if self.unlimited_heal:
            self.hp += amount  # без потолка (Степан)
        else:
            self.hp = min(self.hp + amount, self.max_hp)
        self._healed_total = getattr(self, "_healed_total", 0) + max(0, self.hp - before)

    def __repr__(self):
        return f"<Unit {self.name} {self.attack}/{self.hp}>"
