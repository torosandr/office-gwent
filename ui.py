from telegram_api import send_message, edit_message
import battle as battle_mod
from cards import copy_limit

def back_to_menu_button():
    return [{"text": "↩️ В меню", "callback_data": "to_menu"}]

def build_menu():
    return [
        [{"text": "🎮 Играть", "callback_data": "play_menu"}],
        [{"text": "🃏 Настройка колоды", "callback_data": "deck_edit"}],
        [{"text": "🛒 Магазин", "callback_data": "shop"}],
        [{"text": "🧙 Персонаж", "callback_data": "heroes"}],
        [{"text": "🏆 Рейтинг", "callback_data": "rating"}],
        [{"text": "Обучение", "callback_data": "learn"}],
        [{"text": "Моя коллекция", "callback_data": "my_cards"}],
        [{"text": "Посмотреть все карточки", "callback_data": "view_all_cards"}],
        [{"text": "Мои наборы", "callback_data": "my_sets"}],
        [{"text": "Ввести код", "callback_data": "enter_promo"}],
    ]

def rating_screen(user_id, nickname, rows):
    """Текст экрана рейтинга. user_id — chat_id текущего (для выделения).
    Формат строк: № Ник — Победы / Карты / Монеты. Читается на любом экране."""
    lines = ["🏆 <b>Рейтинг игроков</b>\n"]
    if not rows:
        lines.append("Пока нет игроков.")
    else:
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(rows[:15]):
            mark = medals[i] if i < 3 else f"{i+1}."
            me = " ◀ вы" if str(r['uid']) == str(user_id) else ""
            lines.append(f"{mark} {r['nickname']} — побед {r['wins']}, карт {r['cards']}, 🪙{r.get('coins', 0)}{me}")
    me_wins = next((r['wins'] for r in rows if str(r['uid']) == str(user_id)), 0)
    me_cards = next((r['cards'] for r in rows if str(r['uid']) == str(user_id)), 0)
    me_coins = next((r.get('coins', 0) for r in rows if str(r['uid']) == str(user_id)), 0)
    lines.append(f"\nВаша статистика: {nickname} — побед {me_wins}, карт в коллекции {me_cards}, монет {me_coins} 🪙")
    return "\n".join(lines)

def play_menu_keyboard():
    return [
        [{"text": "⚔️ Создать игру", "callback_data": "duel_create"}],
        [{"text": "🔗 Присоединиться по коду", "callback_data": "duel_join"}],
        [back_to_menu_button()[0]],
    ]

def heroes_screen_text(current_hero):
    return f"🧙 <b>Ваш персонаж</b>\n\nВыберите героя:"

def heroes_keyboard(hero_ids, current):
    """Список кнопок героев для выбора."""
    from config import HEROES
    kb = []
    for hid in hero_ids:
        h = HEROES.get(hid, {})
        mark = "✅ " if hid == current else ""
        tag = "🌟" if h.get('type') == 'passive' else "🧖"
        kb.append([{"text": f"{mark}{tag} {h.get('name', hid)}", "callback_data": f"hero:pick:{hid}"}])
    kb.append([back_to_menu_button()[0]])
    return kb

def hero_detail_text(hid):
    from config import HEROES
    h = HEROES.get(hid, {})
    type_label = "Пассивный" if h.get('type') == 'passive' else "Активный"
    return f"🧙 <b>{h.get('name', hid)}</b>\n\nТип: {type_label}\n\n{h.get('desc', '')}"

def deck_screen_text(deck):
    """Текст текущей колоды: список карт с индексами."""
    if not deck:
        return "🃏 Ваша колода пуста.\nДобавьте карты из коллекции (до 15; обычные — до 2 копий, легендарные — 1)."
    lines = ["🃏 <b>Ваша колода</b>"]
    for i, cid in enumerate(deck):
        info = battle_mod.CARDS.get(cid, {})
        lines.append(f"[{i+1}] {info.get('name', cid)}")
    lines.append(f"\nИтого: {len(deck)}/15 карт")
    return "\n".join(lines)

def deck_main_keyboard():
    return [
        [{"text": "➕ Добавить карту", "callback_data": "deck:add"}],
        [{"text": "➖ Убрать карту", "callback_data": "deck:remove"}],
        [{"text": "💾 Сохранить", "callback_data": "deck:save"}],
        [back_to_menu_button()[0]],
    ]

def deck_add_keyboard(cards, deck=None):
    """Список доступных карт для добавления. deck — текущая колода (для подсчёта копий).
    У карт, достигших лимита копий, кнопка отмечена знаком запрета."""
    deck = deck or []
    from collections import Counter
    counts = Counter(deck)
    kb = []
    for i, cid in enumerate(cards):
        info = battle_mod.CARDS.get(cid, {})
        have = counts.get(cid, 0)
        label = f"➕ {info.get('name', cid)}"
        if have:
            label += f" ×{have}" if have < copy_limit(cid) else f" ⛔×{have}"
        kb.append([{"text": label, "callback_data": f"deck:addcard:{i}"}])
    kb.append([{"text": "↩️ Назад", "callback_data": "deck:main"}])
    return kb

def deck_remove_keyboard(deck):
    """Список карт колоды с кнопками удаления."""
    kb = []
    for i, cid in enumerate(deck):
        info = battle_mod.CARDS.get(cid, {})
        kb.append([{"text": f"➖ {info.get('name', cid)}",
                    "callback_data": f"deck:delcard:{i}"}])
    kb.append([{"text": "↩️ Назад", "callback_data": "deck:main"}])
    return kb

# ==================== МАГАЗИН ====================

def shop_screen_text(coins):
    return f"🛒 <b>Магазин</b>\nВаши монеты: 🪙 {coins}\n\nВыберите карту для покупки:"

def shop_keyboard(items):
    """Кнопки карт магазина. items — список (card_id, name, price, legendary)."""
    kb = []
    for i, (cid, name, price, legendary) in enumerate(items):
        tag = "⭐" if legendary else "•"
        kb.append([{"text": f"{tag} {name} — {price} 🪙", "callback_data": f"shop:buy:{i}"}])
    kb.append([back_to_menu_button()[0]])
    return kb

# ==================== ПРОСМОТР КАРТ ====================

def cards_browser_text(card_ids, page, per_page=10, mode='all'):
    """Текст страницы списка карт. mode: 'all' (все карты) или 'my' (коллекция)."""
    from config import LEGENDARY_CARD_IDS
    total = len(card_ids)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    start = page * per_page
    slice_ids = card_ids[start:start + per_page]
    title = "✨ Все карточки игры" if mode == 'all' else "🃏 Ваша коллекция"
    lines = [f"{title} ({total})", ""]
    for i, cid in enumerate(slice_ids, start=1):
        num = start + i
        card = battle_mod.CARDS.get(cid, {})
        desc = card.get('desc', '')
        short = desc[:35] + ('…' if len(desc) > 35 else '')
        name = card.get('name', cid)
        if cid in LEGENDARY_CARD_IDS:
            name = f"<b><i>{name}</i></b> ⭐"
        lines.append(f"[{num}] {name}")
        if short:
            lines.append(f"   {short}")
    lines.append(f"\nСтраница {page + 1} из {pages}")
    return "\n".join(lines), page, pages

def cards_browser_keyboard(card_ids, page, per_page=10, mode='all'):
    """Кнопки страницы карт: 10 карт + навигация + назад."""
    total = len(card_ids)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    start = page * per_page
    slice_ids = card_ids[start:start + per_page]
    kb = []
    for i, cid in enumerate(slice_ids):
        num = start + i + 1
        kb.append([{"text": f"#{num} {battle_mod.CARDS.get(cid, {}).get('name', cid)}",
                    "callback_data": f"cards:info:{mode}:{cid}:{page}"}])
    # навигация
    nav = []
    if page > 0:
        nav.append({"text": "◀️ Назад", "callback_data": f"cards:{mode}:{page - 1}"})
    if page < pages - 1:
        nav.append({"text": "Вперёд ▶️", "callback_data": f"cards:{mode}:{page + 1}"})
    if nav:
        kb.append(nav)
    kb.append([back_to_menu_button()[0]])
    return kb

def card_info_text(card_id, game, user=None):
    return game.full_card_text(card_id)

def show_main_menu(chat_id, nickname, message_id=None):
    text = f"Привет, {nickname}! Что хотите сделать?"
    if message_id is not None:
        edit_message(chat_id, message_id, text, build_menu())
    else:
        send_message(chat_id, text, build_menu())

def welcome_new(chat_id):
    send_message(
        chat_id,
        "🎮 Добро пожаловать в Офисный Гвинт!\n\n"
        "Правила:\n"
        "• ☕ Кофе — ваш ресурс (начинаете с 3, +1 каждый ход)\n"
        "• 😤 Стресс — ваше здоровье (цель: довести оппонента до 100)\n"
        "• Играйте карты существ и заклинаний\n\n"
        "Введите свой игровой ник:"
    )

def welcome_back(chat_id, nickname):
    send_message(
        chat_id,
        f"🎮 С возвращением, {nickname}!\nРады видеть вас снова. Что хотите сделать?",
        build_menu(),
    )

def ask_nickname_done(chat_id, nickname):
    send_message(
        chat_id,
        f"✨ Привет, {nickname}! 👋\nУ вас есть промокод? Введите его сейчас или нажмите кнопку ниже.",
        [[{"text": "Пропустить и перейти в меню", "callback_data": "skip_promo"}]],
    )

def promo_result(chat_id, message):
    send_message(chat_id, message, [back_to_menu_button()])

def enter_promo_screen(chat_id, message_id):
    edit_message(
        chat_id, message_id,
        "Введите промокод:",
        [[{"text": "↩️ В меню", "callback_data": "to_menu"}]],
    )

# ==================== ИГРА ====================

def duel_created(chat_id, code):
    send_message(
        chat_id,
        f"⚔️ Игра создана!\n\n"
        f"Код для вступления: <b>{code}</b>\n\n"
        f"Передайте его коллеге — пусть отправит боту:\n"
        f"/join {code}",
        [back_to_menu_button()],
    )

def duel_join_prompt(chat_id, message_id):
    edit_message(
        chat_id, message_id,
        "Введите код игры в формате:\n/join КОД\n\nНапример: /join ABCD",
        [back_to_menu_button()],
    )

def duel_joined(chat_id):
    send_message(chat_id, "✅ Вы в игре и ждёте начала...")

def battle_text(game, player_num):
    """Текстовое представление поля глазами игрока player_num (1 или 2)."""
    opp_num = 3 - player_num
    lines = []

    def _board_line(pnum, show_idx=False):
        p = game.players[pnum]
        units = []
        for n, u in enumerate(p.board):
            tag = '💤' if (u.asleep or u.stunned) else ''
            if u.freeze_cycles > 0:
                tag += f"🧊{u.freeze_cycles}"
            if u.status:
                tag += f"[{u.status}]"
            if u.timer is not None:
                tag += f"⏱{u.timer}"
            look = "💀" if not u.is_alive() else f"{u.attack}/{u.hp}"
            prefix = f"#{n+1} " if show_idx else ""
            units.append(f"{prefix}{u.name}({look}){tag}")
        hero = game.hero_name(pnum)
        mark = '🌟' if game.hero_is_passive(pnum) else '🧖'
        return f"☕{p.coffee} 😤{p.stress} | {mark}{hero}\n   " + (', '.join(units) if units else '—')

    lines.append(f"👤 СОПЕРНИК\n{_board_line(opp_num, show_idx=True)}")
    lines.append(f"🫵 ВЫ\n{_board_line(player_num)}")

    my = game.players[player_num]
    hand_lines = []
    active = (game.turn == player_num)
    for i, cid in enumerate(my.hand):
        info = battle_mod.CARDS[cid]
        if active:
            num = f"[{i + 1}] "
        else:
            num = ""
        if info['type'] == 'creature':
            hand_lines.append(f"{num}{info['name']} ({info['attack']}/{info['health']}) за {info['cost']} ☕")
        else:
            hand_lines.append(f"{num}✨ {info['name']} за {info['cost']} ☕")
    lines.append("🃏 Рука:\n" + ("\n".join(hand_lines) if hand_lines else "—"))

    turn_name = game.players[game.turn].name
    lines.append(f"\nХодит: {turn_name}")

    # журнал боя — последние действия
    if game.log:
        lines.append("\n📜 Журнал:")
        for entry in game.log[-6:]:
            lines.append("• " + entry)
    return "\n".join(lines)

def battle_actions_keyboard(game, pnum):
    """Основные кнопки активного игрока: динамическая рука + «Атаковать»."""
    hand_len = len(game.players[pnum].hand)
    kb = []
    # карты руки — сколько есть, столько кнопок
    row = []
    for i in range(hand_len):
        row.append({"text": f"🃏 {i+1}", "callback_data": f"bg:play:{i}"})
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([{"text": "⚔️ Атаковать", "callback_data": "bg:pick_atk"}])
    if game.hero_has_active(pnum):
        kb.append([{"text": "🧖 Герой (способность)", "callback_data": "bg:hero"}])
    else:
        kb.append([{"text": f"🌟 {game.hero_name(pnum)} (пассивный)", "callback_data": "bg:info_hero"}])
    kb.append([{"text": "✔️ Конец хода", "callback_data": "bg:end"}])
    kb.append([{"text": "🏳️ Сдаться", "callback_data": "bg:concede"}])
    kb.append([back_to_menu_button()[0]])
    return kb

def battle_pick_attacker_keyboard(game, pnum):
    """Экран выбора, каким существом атаковать."""
    my = game.players[pnum].board
    kb = []
    row = []
    for i, u in enumerate(my):
        if not u.can_act() or u.attack <= 0:
            continue
        row.append({"text": f"⚔️ #{i+1} {u.name}",
                    "callback_data": f"bg:pick_atk_cre:{i}"})
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([{"text": "↩️ Назад", "callback_data": "bg:cancel"}])
    return kb

def battle_pick_target_keyboard(game, pnum, attacker_idx):
    """Экран выбора цели для выбранного атакующего существа."""
    opp_num = 3 - pnum
    opp = game.players[opp_num].board
    if not (0 <= attacker_idx < len(game.players[pnum].board)):
        raise battle_mod.BattleError('Существо больше недоступно. Выберите атакующего заново.')
    attacker = game.players[pnum].board[attacker_idx]
    if not attacker.can_act() or attacker.attack <= 0:
        raise battle_mod.BattleError('Это существо сейчас не может атаковать.')
    kb = []
    # стрелка в лицо — только если нет блокеров (таунт/супер-таунт)
    has_blocker = any(u.is_alive() and u.is_blocker() for u in opp)
    if not has_blocker:
        kb.append([{"text": "🎯 В лицо герою", "callback_data": f"bg:do_atk:{attacker_idx}:hero"}])
    for i, u in enumerate(opp):
        if not u.is_alive():
            continue
        tag = '⛔' if u.is_super_taunt() else ('🛡' if u.is_taunt() else '')
        kb.append([{"text": f"☠️ {tag}#{i+1} {u.name}({u.attack}/{u.hp})",
                    "callback_data": f"bg:do_atk:{attacker_idx}:{i}"}])
    kb.append([{"text": "↩️ Выбрать другое", "callback_data": "bg:pick_atk"}])
    kb.append([{"text": "↩️ Отмена", "callback_data": "bg:cancel"}])
    return kb

def battle_wait_keyboard():
    """Кнопка для неактивного игрока (ожидание чужого хода)."""
    return [
        [{"text": "🔄 Обновить", "callback_data": "bg:refresh"}],
        [{"text": "🏳️ Сдаться", "callback_data": "bg:concede"}],
    ]

def spell_target_keyboard(game, pnum, hand_idx, spell_status):
    """Экран выбора цели для целевого заклинания.
    hand_idx — карта в руке; spell_status 'урон_цель' или 'хил_цель'."""
    kb = []
    if spell_status == 'урон_цель':
        opp_num = 3 - pnum
        opp = game.players[opp_num].board
        kb.append([{"text": "🎯 Герой соперника", "callback_data": f"bg:cast:{hand_idx}:hero_opp"}])
        for i, u in enumerate(opp):
            if u.is_alive():
                kb.append([{"text": f"☠️ {u.name}({u.hp}хп)", "callback_data": f"bg:cast:{hand_idx}:{i}"}])
    elif spell_status == 'хил_цель':
        my = game.players[pnum].board
        kb.append([{"text": "💚 Свой герой", "callback_data": f"bg:cast:{hand_idx}:hero_self"}])
        for i, u in enumerate(my):
            if u.is_alive():
                kb.append([{"text": f"💚 {u.name}({u.hp}/{u.max_hp})", "callback_data": f"bg:cast:{hand_idx}:{i}"}])
    elif spell_status == 'кража':
        opp_num = 3 - pnum
        opp = game.players[opp_num].board
        for i, u in enumerate(opp):
            if u.is_alive():
                kb.append([{"text": f"☕ Забрать {u.name}({u.attack}/{u.hp})", "callback_data": f"bg:cast:{hand_idx}:{i}"}])
    elif spell_status == 'сокращение':
        my = game.players[pnum].board
        for i, u in enumerate(my):
            if u.is_alive() and not u.is_super_taunt():
                kb.append([{"text": f"🔪 Уничтожить {u.name}({u.attack}/{u.hp})", "callback_data": f"bg:cast:{hand_idx}:{i}"}])
    kb.append([{"text": "↩️ Отмена", "callback_data": "bg:cancel"}])
    return kb
