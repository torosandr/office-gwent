"""Transactional, persistent service for the graphical version of Office Gwent."""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import parse_qsl
from battle import Game, BattleError
from cards import CARDS
from config import BASE_CARD_IDS, HEROES, WIN_COINS, SHOP_PRICES, LEGENDARY_CARD_IDS
from web_state import dump_game, load_game


class WebError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def validate_telegram(init_data, token, now=None):
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs) or not token:
            raise ValueError()
        received = fields.pop('hash')
        secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
        body = '\n'.join(f'{k}={v}' for k, v in sorted(fields.items()))
        expected = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received):
            raise ValueError()
        age = (time.time() if now is None else now) - int(fields['auth_date'])
        if age < -30 or age > 3600:
            raise ValueError()
        user = json.loads(fields['user'])
        if type(user['id']) is not int or user['id'] <= 0 or user.get('is_bot'):
            raise ValueError()
        return user
    except (KeyError, ValueError, TypeError):
        raise WebError('Не удалось подтвердить вход. Откройте игру из Telegram заново.', 401)


class Service:
    def __init__(self, path, local=False, bot_token='', profiles_path=None):
        self.path, self.local, self.bot_token = str(path), local, bot_token
        self.profiles_path = profiles_path
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users(uid TEXT PRIMARY KEY, name TEXT NOT NULL, profile TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, uid TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS rooms(code TEXT PRIMARY KEY, p1 TEXT NOT NULL, p2 TEXT, phase TEXT NOT NULL,
                    snapshot TEXT, version INTEGER NOT NULL DEFAULT 0, awarded INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS membership(uid TEXT PRIMARY KEY, code TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS actions(uid TEXT, request_id TEXT, PRIMARY KEY(uid,request_id));
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            yield db

    def authenticate(self, body, telegram=False):
        if telegram:
            user = validate_telegram(body.get('init_data', ''), self.bot_token)
            uid = str(user['id'])
            name = str(user.get('first_name') or 'Игрок')[:32]
        else:
            if not self.local:
                raise WebError('Локальный вход отключён.', 403)
            entered_id = str(body.get('id') or '').strip()
            name = str(body.get('name') or '').strip()[:32]
            # Вход по игровому ID из users.json бота: позволяет подтянуть колоду, героя и статистику.
            if entered_id:
                original = self._bot_profile(entered_id)
                if original is None:
                    raise WebError('Игрок с таким ID не найден среди пользователей бота.', 404)
                uid = entered_id
                name = name or str(original.get('nickname') or 'Игрок')[:32]
            else:
                if not name:
                    raise WebError('Введите имя игрока.')
                uid = 'local-' + secrets.token_hex(12)
        with self.transaction() as db:
            if not db.execute('SELECT 1 FROM users WHERE uid=?', (uid,)).fetchone():
                profile = {'wins': 0, 'coins': 100, 'hero': 'режиссер', 'deck': [], 'collection': {}}
                original = self._bot_profile(uid)
                if original:
                    for key in ('wins', 'coins', 'hero', 'deck', 'collection'):
                        if key in original:
                            profile[key] = original.get(key, profile[key])
                        elif key == 'collection':
                            profile[key] = {}
                db.execute('INSERT INTO users VALUES(?,?,?)', (uid, name, json.dumps(profile, ensure_ascii=False)))
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), uid, time.time()+7*86400))
        return {'token': token, **self.state(uid)}

    def _bot_profile(self, uid):
        """Ищет профиль игрока в users.json бота по id. Возвращает dict или None."""
        try:
            with open(self.profiles_path, encoding='utf-8') as stream:
                data = json.load(stream)
            return data.get(str(uid))
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    def identify(self, token):
        with self.connect() as db:
            row = db.execute('SELECT uid FROM sessions WHERE token=? AND expires>?',
                             (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        if not row:
            raise WebError('Войдите в игру заново.', 401)
        return row['uid']

    def _room(self, db, uid):
        return db.execute('SELECT r.* FROM rooms r JOIN membership m ON r.code=m.code WHERE m.uid=?', (uid,)).fetchone()

    def _profile(self, db, uid):
        row = db.execute('SELECT * FROM users WHERE uid=?', (uid,)).fetchone()
        return {'id': uid, 'name': row['name'], **json.loads(row['profile'])}

    def state(self, uid):
        with self.connect() as db:
            db.execute('BEGIN')
            return self._state(db, uid)

    def _state(self, db, uid):
        profile = self._profile(db, uid)
        row = self._room(db, uid)
        result = {'profile': {k: profile[k] for k in ('id', 'name', 'wins', 'coins')}, 'room': None, 'local': self.local}
        if row is None:
            return result
        room = {'code': row['code'], 'version': row['version'], 'phase': row['phase'],
                'names': [self._profile(db, row['p1'])['name'], self._profile(db, row['p2'])['name'] if row['p2'] else None]}
        result['room'] = room
        if not row['snapshot']:
            return result
        game = load_game(json.loads(row['snapshot']))
        me = 1 if row['p1'] == uid else 2
        def side(number):
            p = game.players[number]
            board = []
            for index, u in enumerate(p.board):
                targets = []
                if number == me:
                    for target in ['hero'] + [str(i) for i in range(len(game.players[3-me].board))]:
                        try:
                            game.can_attack(me, index, target)
                            targets.append(target)
                        except BattleError:
                            pass
                board.append({'index': index, 'card': u.card, 'name': u.name, 'attack': u.attack,
                              'hp': u.hp, 'max_hp': u.max_hp, 'status': u.status, 'asleep': u.asleep,
                              'stunned': u.stunned, 'frozen': u.freeze_cycles, 'attacked': u.attacked,
                              'deadline': u.timer if u.status == 'дедлайн' else None,
                              'targets': targets, 'desc': CARDS[u.card].get('desc', '')})
            return {'name': p.name, 'stress': p.stress, 'coffee': p.coffee, 'board': board,
                    'hand_count': len(p.hand), 'deck_count': len(p.deck), 'hero': game.hero_name(number)}
        room.update({'me': side(me), 'opponent': side(3-me), 'my_turn': game.turn == me,
                     'hero_ready': game.can_use_hero(me)[0], 'skip': game.players[me].skip_actions,
                     'hero_info': HEROES.get(game.players[me].hero_id, {}),
                     'log': game.log[-8:], 'won': game.winner == me if game.winner else None, 'hand': []})
        for index, cid in enumerate(game.players[me].hand):
            info = CARDS[cid]
            ok, reason = game.can_play(me, index)
            targets = []
            if game.is_targeted(cid) and ok:
                status = info['status']
                own = status in ('хил_цель', 'сокращение')
                candidates = ['hero_self' if own else 'hero_opp'] + [str(i) for i in range(len(game.players[me if own else 3-me].board))]
                for target in candidates:
                    try:
                        game._validate_spell_target(me, status, target)
                        targets.append(target)
                    except BattleError:
                        pass
            room['hand'].append({**info, 'id': cid, 'index': index, 'playable': ok,
                                 'reason': reason, 'targeted': game.is_targeted(cid), 'targets': targets})
        return result

    # ---------- Магазин / колода / карты ----------

    def _profile_json(self, db, uid):
        row = db.execute('SELECT profile FROM users WHERE uid=?', (uid,)).fetchone()
        return json.loads(row['profile'])

    def _save_profile(self, db, uid, profile):
        clean = {k: v for k, v in profile.items() if k not in ('id', 'name')}
        db.execute('UPDATE users SET profile=? WHERE uid=?', (json.dumps(clean, ensure_ascii=False), uid))

    def menu(self, uid):
        """Сводка для внеигрового меню: имя, монеты, колода, доступные карты."""
        with self.connect() as db:
            row = db.execute('SELECT name, profile FROM users WHERE uid=?', (uid,)).fetchone()
            profile = json.loads(row['profile'])
        return {
            'name': row['name'],
            'coins': profile.get('coins', 0),
            'wins': profile.get('wins', 0),
            'deck': profile.get('deck', []),
            'collection': profile.get('collection', {}),
        }

    def rating(self):
        """Список игроков по победам (для вкладки «Рейтинг»)."""
        with self.connect() as db:
            rows = db.execute('SELECT uid, name, profile FROM users').fetchall()
        items = []
        for row in rows:
            prof = json.loads(row['profile'])
            if not row['name']:
                continue
            items.append({'name': row['name'], 'wins': prof.get('wins', 0),
                          'coins': prof.get('coins', 0)})
        items.sort(key=lambda x: (-x['wins'], -x['coins'], x['name']))
        return items

    def cards_catalog(self, uid):
        """Все карты игры с пометкой легендарности и наличия в коллекции."""
        with self.connect() as db:
            profile = self._profile_json(db, uid)
        owned = set(profile.get('collection', {}).keys())
        items = []
        for cid, card in CARDS.items():
            items.append({
                'id': cid, 'name': card.get('name', cid), 'type': card.get('type'),
                'cost': card.get('cost', 0), 'attack': card.get('attack', 0),
                'health': card.get('health', 0), 'status': card.get('status'),
                'desc': card.get('desc', ''), 'legendary': cid in LEGENDARY_CARD_IDS,
                'price': SHOP_PRICES.get(cid),
                'for_sale': cid in SHOP_PRICES,
                'owned': cid in owned, 'count': profile.get('collection', {}).get(cid, 0),
            })
        return items

    def buy(self, uid, card_id):
        if card_id not in SHOP_PRICES or card_id not in CARDS:
            raise WebError('Этой карты нет в магазине.', 404)
        with self.transaction() as db:
            profile = self._profile_json(db, uid)
            price = SHOP_PRICES[card_id]
            coins = profile.get('coins', 0)
            if coins < price:
                raise WebError(f'Не хватает монет: нужно {price}, у вас {coins}.')
            have = profile.get('collection', {}).get(card_id, 0)
            if card_id in LEGENDARY_CARD_IDS:
                if have >= 1:
                    raise WebError('Легендарную карту можно купить только 1 раз.')
            elif have >= 2:
                raise WebError('Обычной карты нельзя иметь больше 2 копий.')
            profile['coins'] = coins - price
            profile.setdefault('collection', {})
            profile['collection'][card_id] = have + 1
            self._save_profile(db, uid, profile)
        return self.menu(uid)

    def deck_mutate(self, uid, op, card_id=None, index=None):
        """op: 'add' (карта из коллекции/базовых), 'remove' (по индексу), 'save' (подтвердить)."""
        with self.transaction() as db:
            profile = self._profile_json(db, uid)
            deck = list(profile.get('deck', []) or [])
            if op == 'add':
                if card_id not in CARDS:
                    raise WebError('Карта не найдена.', 404)
                if len(deck) >= 15:
                    raise WebError('В колоде уже 15 карт — максимум.')
                if deck.count(card_id) >= 2:
                    raise WebError('Нельзя больше 2 копий одной карты.')
                deck.append(card_id)
            elif op == 'remove':
                if index is None or not (0 <= index < len(deck)):
                    raise WebError('Некорректная позиция карты.')
                deck.pop(index)
            elif op == 'save':
                own_cards = sum(profile.get('collection', {}).values())
                if len(deck) != 15 and own_cards >= 15:
                    raise WebError(f'Нужно ровно 15 карт, сейчас {len(deck)}.')
            else:
                raise WebError('Неизвестная операция.', 404)
            profile['deck'] = deck
            self._save_profile(db, uid, profile)
        return self.menu(uid)

    def deck_candidates(self, uid):
        """Карты, из которых можно собирать колоду: базовые + из коллекции."""
        with self.connect() as db:
            profile = self._profile_json(db, uid)
        owned = set(profile.get('collection', {}).keys()) | set(BASE_CARD_IDS)
        return sorted((cid for cid in CARDS if cid in owned),
                      key=lambda c: CARDS[c].get('name', c))

    def mutate(self, uid, operation, body):
        request_id = body.get('request_id')
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', request_id):
            raise WebError('Некорректный номер действия.')
        with self.transaction() as db:
            if db.execute('SELECT 1 FROM actions WHERE uid=? AND request_id=?', (uid, request_id)).fetchone():
                return self._state(db, uid)
            room = self._room(db, uid)
            if operation in ('create', 'join'):
                if room and room['phase'] not in ('finished', 'closed'):
                    raise WebError('Вы уже участвуете в партии.', 409)
                db.execute('DELETE FROM membership WHERE uid=?', (uid,))
                if operation == 'create':
                    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
                    while True:
                        code = ''.join(secrets.choice(alphabet) for _ in range(6))
                        if not db.execute('SELECT 1 FROM rooms WHERE code=?', (code,)).fetchone():
                            break
                    db.execute('INSERT INTO rooms(code,p1,phase) VALUES(?,?,?)', (code, uid, 'waiting'))
                else:
                    code = str(body.get('code', '')).strip().upper()
                    target = db.execute('SELECT * FROM rooms WHERE code=?', (code,)).fetchone()
                    if not target or target['phase'] != 'waiting' or target['p1'] == uid:
                        raise WebError('Свободная партия с таким кодом не найдена.', 404)
                    p1, p2 = self._profile(db, target['p1']), self._profile(db, uid)
                    def deck(p):
                        selected = [c for c in p.get('deck', []) if c in CARDS][:15]
                        return selected if selected else BASE_CARD_IDS * 2
                    game = Game(p1['name'], p2['name'], deck1=deck(p1), deck2=deck(p2),
                                hero1=p1.get('hero'), hero2=p2.get('hero'))
                    game.start()
                    db.execute('UPDATE rooms SET p2=?,phase=?,snapshot=?,version=version+1 WHERE code=?',
                               (uid, 'active', json.dumps(dump_game(game), ensure_ascii=False), code))
                db.execute('INSERT INTO membership VALUES(?,?)', (uid, code))
            elif operation == 'leave':
                if room and room['phase'] == 'active':
                    raise WebError('Сначала завершите партию или сдавайтесь.')
                if room and room['phase'] == 'waiting':
                    db.execute("UPDATE rooms SET phase='closed',version=version+1 WHERE code=?", (room['code'],))
                db.execute('DELETE FROM membership WHERE uid=?', (uid,))
            elif operation == 'action':
                if not room or room['phase'] != 'active':
                    raise WebError('Нет активной партии.', 409)
                if type(body.get('version')) is not int or body['version'] != room['version']:
                    raise WebError('Поле уже изменилось. Выберите действие заново.', 409)
                game = load_game(json.loads(room['snapshot']))
                me = 1 if room['p1'] == uid else 2
                action = body.get('action')
                if action == 'concede':
                    game.phase, game.winner = 'finished', 3-me
                    game.winner_name = game.players[3-me].name
                    game._log(f'{game.players[me].name} сдаётся.')
                else:
                    if game.turn != me:
                        raise WebError('Сейчас ход соперника.')
                    index = body.get('index')
                    if action in ('play', 'cast', 'attack') and (type(index) is not int or index < 0):
                        raise WebError('Выберите карту или существо.')
                    try:
                        if action == 'play':
                            game.play_card(me, index)
                        elif action == 'cast':
                            game.cast_targeted_spell(me, index, str(body.get('target', '')))
                        elif action == 'attack':
                            game.attack(me, index, str(body.get('target', '')))
                        elif action == 'hero':
                            game.use_hero(me)
                        elif action == 'end':
                            game.end_turn()
                        else:
                            raise WebError('Неизвестное действие.')
                    except BattleError as error:
                        raise WebError(str(error))
                awarded = room['awarded']
                if game.phase == 'finished' and not awarded:
                    winner = room['p1'] if game.winner == 1 else room['p2']
                    profile = self._profile(db, winner)
                    profile['wins'] += 1
                    profile['coins'] += WIN_COINS
                    db.execute('UPDATE users SET profile=? WHERE uid=?', (json.dumps({k: v for k, v in profile.items() if k not in ('id', 'name')}, ensure_ascii=False), winner))
                    awarded = 1
                db.execute('UPDATE rooms SET snapshot=?,phase=?,awarded=?,version=version+1 WHERE code=?',
                           (json.dumps(dump_game(game), ensure_ascii=False), game.phase, awarded, room['code']))
            else:
                raise WebError('Неизвестный запрос.', 404)
            db.execute('INSERT INTO actions VALUES(?,?)', (uid, request_id))
            return self._state(db, uid)
