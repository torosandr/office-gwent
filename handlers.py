import battle
from config import HEROES
from telegram_api import edit_message, send_message
from ui import (
    back_to_menu_button,
    show_main_menu,
    welcome_new,
    welcome_back,
    ask_nickname_done,
    promo_result,
    enter_promo_screen,
    play_menu_keyboard,
    duel_join_prompt,
    battle_text,
    battle_actions_keyboard,
    battle_pick_attacker_keyboard,
    battle_pick_target_keyboard,
    battle_wait_keyboard,
    rating_screen,
    spell_target_keyboard,
    shop_screen_text,
    shop_keyboard,
    cards_browser_text,
    cards_browser_keyboard,
    heroes_screen_text,
    heroes_keyboard,
    hero_detail_text,
    deck_screen_text,
    deck_main_keyboard,
)
from match import MatchManager
from admin_commands import AdminMixin
from deck_commands import DeckMixin
from battle_messages import update_battle_message


class Handlers(AdminMixin, DeckMixin):
    def __init__(self, store, games, ui_build_menu):
        self.store = store          # UserStore
        self.games = games          # GameData
        self.build_menu = ui_build_menu
        self.matches = MatchManager()

    def _set_state(self, user, state):
        if user.get('state') != state:
            user['state'] = state
            self.store.persist()

    def _battle_message(self, match, chat_id, text, keyboard, force=False):
        update_battle_message(match, chat_id, text, keyboard,
                              send_message, edit_message, force=force)

    # ================= ТЕКСТ =================

    def handle_text(self, chat_id, text):
        user = self.store.get(chat_id)
        state = user.get('state', 'start')

        if text.strip().split(maxsplit=1)[0:1] == ['/play']:
            self._duel_create(chat_id, None, user.get('nickname', '?'))
            return

        if text.startswith("/join"):
            code = text[len("/join"):].strip()
            self._process_join(chat_id, code, user)
            return
        if text.startswith("/stopgame") or text.startswith("/stop"):
            self._stop_game(chat_id)
            return
        if text.startswith("/broadcast"):
            self._broadcast(chat_id, text)
            return
        if text.startswith("/reload"):
            self._reload_data(chat_id)
            return
        if text.startswith("/setwins"):
            self._set_wins(chat_id, text)
            return
        if text.startswith("/addcoins"):
            self._add_coins(chat_id, text)
            return
        if text.startswith("/givecard"):
            self._give_card(chat_id, text)
            return
        if text.startswith("/giveset"):
            self._give_set(chat_id, text)
            return
        if text.startswith("/help"):
            self._send_help(chat_id)
            return
        if text.startswith("/my_id"):
            send_message(chat_id, f"🆔 Ваш игровой ID: <code>{chat_id}</code>\n\nЕго можно использовать для входа в графическую версию игры (мини-апп) — при входе укажите этот ID владельцу.")
            return
        if text.startswith("/start"):
            if user.get('nickname'):
                self._set_state(user, 'menu')
                welcome_back(chat_id, user['nickname'])
            else:
                self._set_state(user, 'nickname')
                welcome_new(chat_id)
            return
        if state == 'nickname':
            user['nickname'] = text.strip()
            user['state'] = 'promo'
            self.store.persist()
            ask_nickname_done(chat_id, user['nickname'])
            return
        if state == 'promo':
            ok, message = self.games.redeem_promo(user, text, self.store)
            promo_result(chat_id, message)
            user['state'] = 'menu'
            self.store.persist()
            return

        # если в матче и набирает число — пробуем сыграть карту
        code, match = self.matches.match_of(chat_id)
        if match and match.get('game') and text.strip().isdigit():
            self._play_card(chat_id, code, int(text.strip()) - 1)
            return

        send_message(chat_id, "Не понял команду. Используйте /start или кнопки меню.")

    # ================= СПРАВКА =================

    def _help_text(self):
        return (
            "🎮 <b>Офисный Гвинт — как играть</b>\n\n"
            "<b>Цель:</b> довести стресс соперника (😤) до 0.\n\n"
            "<b>Ресурс — Кофе (☕):</b>\n"
            "• Старт — 3, +1 в начале каждого хода (максимум 10)\n"
            "• Кофе тратится на розыгрыш карт и способность героя\n\n"
            "<b>Персонажи:</b>\n"
            "• 🧖 Режиссер монтажа — активная: −2☕, +3 стресса себе\n"
            "• 🌟 Мария Рыбина — пассивная: все ваши существа +1 к атаке и здоровью\n\n"
            "<b>Героя можно выбрать в меню «🧙 Персонаж».</b>\n\n"
            "<b>Как идёт ход:</b>\n"
            "1. +1 кофе, добор 1 карты\n"
            "2. Разыграй карты (сколько хватает кофе)\n"
            "3. Атакуй существами (каждое — 1 раз за ход)\n"
            "4. Заверши ход (кнопка «✔️ Конец хода»)\n\n"
            "<b>Атака:</b>\n"
            "• Существо бьёт в лицо герою ИЛИ по существу соперника\n"
            "• Бой обоюдный: оба получают урон\n"
            "• Только что сыгранное существо спит 💤 и не атакует\n"
            "• Таунт 🛡 блокирует атаки в лицо, пока жив\n\n"
            "<b>Команды:</b>\n"
            "/start — начать, вернуться в меню\n"
            "/play — создать игру (или кнопка «🎮 Играть»)\n"
            "/join КОД — вступить в игру по коду\n"
            "/help — эта справка"
        )

    def _send_help(self, chat_id):
        send_message(chat_id, self._help_text())

    # ================= ЛОББИ / МАТЧ =================

    def _process_join(self, chat_id, code, user):
        code = code.strip().upper()
        ok, _ = self.matches.join(code, chat_id, user.get('nickname', "?"))
        if not ok:
            send_message(chat_id, "❌ Не удалось вступить в игру: попробуйте другой код.")
            return
        m2 = self.matches.matches[code.upper()]
        p1 = m2["p1"]
        game = m2["game"]
        if game is None:
            p2 = m2["p2"]
            deck1 = list(self.store.get(p1).get('deck', []))
            deck2 = list(self.store.get(p2).get('deck', []))
            hero1 = self.store.get(p1).get('hero', 'режиссер')
            hero2 = self.store.get(p2).get('hero', 'режиссер')
            game = self.matches.start_game(code.upper(), deck1=deck1, deck2=deck2,
                                           hero1=hero1, hero2=hero2)
        self._push_battle(code)

    def _stop_game(self, chat_id):
        code, opp = self.matches.leave_for(chat_id)
        if code is None:
            send_message(chat_id, "Вы не состоите ни в одной партии.")
            return
        send_message(chat_id, "🛑 Партия завершена. Вы вышли из матча.", [back_to_menu_button()])
        if opp is not None and opp != chat_id:
            send_message(opp, "🛑 Соперник вышел из матча. Партия завершена.", [back_to_menu_button()])

    def _concede(self, code, chat_id, pnum, m, g):
        m['attack_state'] = None
        g.phase = 'finished'
        g.winner = self._opp_num_in_match(m, pnum)
        g.winner_name = m["p1_name"] if g.winner == 1 else m["p2_name"]
        self._finish_match(code, m, g, concede=True, conceder_chat=chat_id)

    def _opp_num_in_match(self, m, pnum):
        return 2 if pnum == 1 else 1

    def _finish_match(self, code, m, g, concede=False, conceder_chat=None):
        if not m.get('winner_awarded'):
            winner_chat = m["p1"] if g.winner == 1 else m["p2"]
            from config import WIN_COINS
            self.store.award_win(winner_chat, WIN_COINS)
            m['winner_awarded'] = True

        for pid in (m["p1"], m["p2"]):
            pnum = 1 if pid == m["p1"] else 2
            text = battle_text(g, pnum)
            if concede:
                conceder_name = m["p1_name"] if m["p1"] == conceder_chat else m["p2_name"]
                if pid == conceder_chat:
                    ending = "Вы сдались. Победитель: " + g.winner_name
                else:
                    ending = f"Соперник {conceder_name} сдался. Вы победили! 🏆"
            else:
                me = 'Вы победили! 🏆' if pid == (m["p1"] if g.winner == 1 else m["p2"]) else 'Вы проиграли... 😞'
                ending = f"{me}\n<b>Победитель: {g.winner_name}</b>"
            self._battle_message(m, pid, f"{text}\n\n{ending}", [back_to_menu_button()])

        self.matches.drop(code)

    def _push_battle(self, code, force_chat=None):
        m = self.matches.matches[code]
        g = m["game"]
        active = m["p1"] if g.turn == 1 else m["p2"]
        if g.phase == 'finished':
            self._finish_match(code, m, g)
            return
        m['attack_state'] = None

        for pid in (m["p1"], m["p2"]):
            pnum = 1 if pid == m["p1"] else 2
            text = battle_text(g, pnum)
            if pid == active:
                self._battle_message(m, pid, text, battle_actions_keyboard(g, pnum), force=pid == force_chat)
            else:
                self._battle_message(m, pid, text + "\n\nОжидание соперника...", battle_wait_keyboard(), force=pid == force_chat)

    def games_hero_desc(self, g, pnum):
        from config import HEROES
        info = HEROES.get(g.players[pnum].hero_id, {})
        return info.get('desc', '')

    # ================= КЛЕЙ-КНОПКИ =================

    def handle_callback(self, chat_id, message_id, data):
        user = self.store.get(chat_id)
        nickname = user.get('nickname', "?")

        if data.startswith("bg:"):
            self._handle_battle_key(chat_id, data)
            return

        # Меню может заменить содержимое того же сообщения с полем.
        _, match = self.matches.match_of(chat_id)
        cached = (match or {}).get('battle_messages', {}).get(chat_id)
        if cached and cached['id'] == message_id:
            cached['content'] = None

        if data.startswith("deck:"):
            self.handle_deck(chat_id, message_id, data, user)
            return
        if data == "deck_edit":
            edit_message(chat_id, message_id, deck_screen_text(user.get('deck', [])), deck_main_keyboard())
            return

        if data.startswith("shop:"):
            self._handle_shop(data, chat_id, message_id, user)
            return
        if data == "shop":
            items = self.games.shop_items()
            edit_message(chat_id, message_id, shop_screen_text(user.get('coins', 0)), shop_keyboard(items))
            return

        if data.startswith("cards:"):
            self._handle_cards(data, chat_id, message_id, user)
            return

        if data.startswith("hero:"):
            hid = data.split(":")[2]
            if hid in HEROES:
                if user.get('hero') != hid:
                    user['hero'] = hid
                    self.store.persist()
                send_message(chat_id, f"✅ Выбран герой: {HEROES[hid]['name']}")
                edit_message(chat_id, message_id, hero_detail_text(hid),
                             [[{"text": "↩️ К выбору", "callback_data": "heroes"}],
                              [back_to_menu_button()[0]]])
            return

        # простые одиночные пункты меню
        handlers = {
            "play_menu": lambda: edit_message(chat_id, message_id, "⚔️ Выберите действие:", play_menu_keyboard()),
            "heroes": lambda: edit_message(chat_id, message_id, heroes_screen_text(user.get('hero', 'режиссер')),
                                          heroes_keyboard(list(HEROES.keys()), user.get('hero', 'режиссер'))),
            "rating": lambda: edit_message(chat_id, message_id,
                                           rating_screen(chat_id, nickname, self.store.ranking()),
                                           [back_to_menu_button()]),
            "my_cards": lambda: self._cards_page(chat_id, message_id, user, 'my'),
            "view_all_cards": lambda: self._cards_page(chat_id, message_id, user, 'all'),
            "duel_join": lambda: duel_join_prompt(chat_id, message_id),
            "my_sets": self._my_sets(chat_id, message_id, user),
            "open_sets": lambda: edit_message(chat_id, message_id, "Здесь будут наборы, которые можно открыть.",
                                              [back_to_menu_button()]),
            "learn": lambda: edit_message(chat_id, message_id, self._help_text(), [back_to_menu_button()]),
            "to_menu": self._to_menu(chat_id, message_id, message_id, user),
            "skip_promo": self._to_menu(chat_id, message_id, message_id, user),
        }
        # duel_create и enter_promo обрабатываются отдельно из-за переходов
        if data == "duel_create":
            self._duel_create(chat_id, message_id, nickname)
            return
        if data == "enter_promo":
            self._set_state(user, 'promo')
            enter_promo_screen(chat_id, message_id)
            return

        fn = handlers.get(data)
        if fn:
            if callable(fn):
                fn()
            return

    def _to_menu(self, chat_id, message_id, _mid, user):
        def go():
            self._set_state(user, 'menu')
            show_main_menu(chat_id, user.get('nickname', "?"), message_id)
        return go

    def _duel_create(self, chat_id, message_id, nickname):
        code, match = self.matches.match_of(chat_id)
        if match:
            if message_id is None:
                send_message(chat_id, "Вы уже в игре!")
            else:
                edit_message(chat_id, message_id, "Вы уже в игре!")
            return
        code = self.matches.create(chat_id, nickname)
        if message_id is not None:
            edit_message(chat_id, message_id, "⚔️ Игра создана!", [back_to_menu_button()])
        send_message(chat_id, f"Код для вступления: <b>{code}</b>\n\nПередайте код коллеге — пусть отправит:\n/join {code}",
                     [back_to_menu_button()])

    def _cards_page(self, chat_id, message_id, user, mode):
        card_ids = self.games.card_id_list(user) if mode == 'my' else self.games.card_id_list()
        if mode == 'my' and not card_ids:
            edit_message(chat_id, message_id, "🃏 Ваша коллекция пуста. Откройте набор или введите промокод.",
                         [back_to_menu_button()])
            return
        text, page, pages = cards_browser_text(card_ids, 0, mode=mode)
        edit_message(chat_id, message_id, text, cards_browser_keyboard(card_ids, 0, mode=mode))

    def _my_sets(self, chat_id, message_id, user):
        def go():
            sets = user.get('sets', [])
            text = ("У вас пока нет открытых наборов." if not sets
                    else "📦 Ваши наборы:\n" + "\n".join(f"• {self.games.set_name(s)}" for s in sets))
            edit_message(chat_id, message_id, text, [back_to_menu_button()])
        return go

    def _handle_cards(self, data, chat_id, message_id, user):
        if data.startswith("cards:info:"):
            _, _, mode, cid, page = data.split(":")[:5]
            back = [[{"text": "↩️ К списку", "callback_data": f"cards:{mode}:{page}"}]]
            edit_message(chat_id, message_id, self.games.full_card_text(cid), back)
            return
        _, mode, page_s = data.split(":")[:3]
        card_ids = self.games.card_id_list(user) if mode == 'my' else self.games.card_id_list()
        text, page, pages = cards_browser_text(card_ids, int(page_s), mode=mode)
        edit_message(chat_id, message_id, text, cards_browser_keyboard(card_ids, int(page_s), mode=mode))

    def _handle_shop(self, data, chat_id, message_id, user):
        items = self.games.shop_items()
        if data.startswith("shop:buy:"):
            idx = int(data.split(":")[2])
            if not (0 <= idx < len(items)):
                return
            cid, name, price, legend = items[idx]
            edit_message(chat_id, message_id, f"Купить {name} за {price} 🪙?",
                         [[{"text": "✅ Купить", "callback_data": f"shop:confirm:{idx}"}],
                          [{"text": "↩️ Назад", "callback_data": "shop"}]])
            return
        if data.startswith("shop:confirm:"):
            idx = int(data.split(":")[2])
            if not (0 <= idx < len(items)):
                return
            cid, name, price, legend = items[idx]
            ok, msg = self.games.buy_card(user, cid)
            if ok:
                self.store.persist()
            edit_message(chat_id, message_id, msg, [back_to_menu_button()])

    # ================= БОЕВЫЕ КНОПКИ =================

    def _handle_battle_key(self, chat_id, data):
        code, match = self.matches.match_of(chat_id)
        if not match or not match.get('game'):
            send_message(chat_id, "Вы не в активной игре.")
            return
        g = match['game']
        pnum = 1 if match["p1"] == chat_id else 2
        m = match

        action = data[3:]

        if action == "pick_atk":
            if g.turn != pnum:
                send_message(chat_id, "Сейчас не ваш ход.")
                return
            m['attack_state'] = 'pick_attacker'
            self._battle_message(m, chat_id, "Каким существом атаковать?", battle_pick_attacker_keyboard(g, pnum))
            return
        if action.startswith("pick_atk_cre:"):
            if g.turn != pnum:
                send_message(chat_id, "Сейчас не ваш ход.")
                return
            try:
                attacker = int(action.split(":")[1])
                keyboard = battle_pick_target_keyboard(g, pnum, attacker)
            except (ValueError, battle.BattleError) as e:
                m['attack_state'] = None
                send_message(chat_id, f"⛔ {e}")
                return
            m['attack_state'] = ('pick_target', attacker)
            self._battle_message(m, chat_id, "Выберите цель:", keyboard)
            return
        if action == "cancel":
            m['attack_state'] = None
            self._push_battle(code)
            return
        if action == "refresh":
            self._push_battle(code, force_chat=chat_id)
            return
        if action == "concede":
            self._concede(code, chat_id, pnum, m, g)
            return

        try:
            if g.turn != pnum:
                raise battle.BattleError("Сейчас не ваш ход.")
            if action == "end":
                g.end_turn()
            elif action == "hero":
                g.use_hero(pnum)
            elif action == "info_hero":
                send_message(chat_id, f"🌟 {g.hero_name(pnum)}\n{self.games_hero_desc(g, pnum)}")
                return
            elif action.startswith("do_atk:"):
                _, attacker, target = action.split(":")[:3]
                g.attack(pnum, int(attacker), target)
            elif action.startswith("cast:"):
                _, hand_idx, target = action.split(":")[:3]
                g.cast_targeted_spell(pnum, int(hand_idx), target)
            elif action.startswith("play:"):
                idx = int(action.split(":")[1])
                self._play_card(chat_id, code, idx)
                return
            elif action == "refresh":
                pass
        except (battle.BattleError, ValueError) as e:
            m['attack_state'] = None
            send_message(chat_id, f"⛔ {e}")
            return

        m['attack_state'] = None
        self._push_battle(code)

    def _play_card(self, chat_id, code, idx):
        _, match = self.matches.match_of(chat_id)
        if not match or not match.get('game'):
            send_message(chat_id, "Вы не в активной игре.")
            return
        g = match['game']
        pnum = 1 if match["p1"] == chat_id else 2
        ok, err = g.can_play(pnum, idx)
        if not ok:
            send_message(chat_id, f"⛔ {err}")
            return
        card_id = g.players[pnum].hand[idx]
        if g.is_targeted(card_id):
            status = battle.CARDS[card_id].get('status')
            self._battle_message(match, chat_id, "Выберите цель:", spell_target_keyboard(g, pnum, idx, status))
            return
        try:
            g.play_card(pnum, idx)
        except battle.BattleError as e:
            send_message(chat_id, f"⛔ {e}")
            return
        self._push_battle(code)
