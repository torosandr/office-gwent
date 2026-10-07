"""Transactional Mini App rewards; shared redemption ledger with the webhook bot."""
import json
import secrets
from pathlib import Path
from cards import CARDS
from config import FILES, HEROES, BASE_CARD_IDS, LEGENDARY_CARD_IDS


class Rewards:
    def init_rewards(self):
        with self.transaction() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS promo_claims(code TEXT, uid TEXT, PRIMARY KEY(code,uid));
              CREATE TABLE IF NOT EXISTS packs(id TEXT PRIMARY KEY, uid TEXT NOT NULL,
                  set_id TEXT, name TEXT NOT NULL, cards TEXT NOT NULL, opened INTEGER NOT NULL DEFAULT 0);
            ''')

    def reward_catalog(self, key):
        path = getattr(self, 'reward_files', {}).get(key) or Path(__file__).parent / FILES[key]
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (OSError, ValueError):
            from web_service import WebError
            raise WebError('Каталог наград временно недоступен.', 503)

    def collection_counts(self, uid, profile):
        collection = dict(profile.get('collection', {}))
        original = self._bot_profile(uid) or {}
        for cid, count in original.get('collection', {}).items():
            if isinstance(count, int) and count > 0:
                collection[cid] = max(collection.get(cid, 0), count)
        return collection

    def heroes(self, uid):
        with self.connect() as db:
            current = self._profile_json(db, uid).get('hero', 'режиссер')
        return {'selected': current, 'heroes': [{'id': key, **value} for key, value in HEROES.items()]}

    def select_hero(self, uid, hero):
        from web_service import WebError
        if hero not in HEROES:
            raise WebError('Персонаж не найден.', 404)
        with self.transaction() as db:
            p = self._profile_json(db, uid)
            p['hero'] = hero
            self._save_profile(db, uid, p)
        return self.heroes(uid)

    def my_packs(self, uid):
        with self.connect() as db:
            rows = db.execute('SELECT id,name,cards FROM packs WHERE uid=? AND opened=0 ORDER BY id', (uid,)).fetchall()
        return [{'id': x['id'], 'name': x['name'], 'size': len(json.loads(x['cards']))} for x in rows]

    def redeem_promo(self, uid, code, immediate=False):
        from web_service import WebError
        if not isinstance(code, str) or not code.strip() or len(code) > 100:
            raise WebError('Введите промокод.')
        catalog = self.reward_catalog('codes')
        key = next((x for x in catalog if x.casefold() == code.strip().casefold()), None)
        if key is None:
            raise WebError('Неверный промокод.')
        promo = catalog[key]
        if not isinstance(promo, dict):
            raise WebError('Промокод недоступен.')
        used = {str(x.get('id')) for x in promo.get('used_by', []) if isinstance(x, dict)}
        target = promo.get('target')
        if promo.get('type') == 'set':
            reward = self.reward_catalog('sets').get(target)
            if not isinstance(reward, dict):
                raise WebError('Набор не найден.', 404)
            cards, name = reward.get('cards', []), reward.get('name', target)
        elif promo.get('type') == 'card' and target in CARDS:
            cards, name = [target], 'Пакетик: ' + CARDS[target]['name']
        else:
            raise WebError('Награда не найдена.', 404)
        if not cards or any(cid not in CARDS for cid in cards):
            raise WebError('Состав набора недоступен.', 503)
        canonical = key.casefold()
        with self.transaction() as db:
            used |= {x['uid'] for x in db.execute('SELECT uid FROM promo_claims WHERE code=?', (canonical,))}
            if str(uid) in used:
                raise WebError('Вы уже использовали этот промокод.')
            if len(used) >= promo.get('limit', 1):
                raise WebError('Лимит применений промокода исчерпан.')
            row = db.execute('SELECT uid FROM users WHERE uid=?', (uid,)).fetchone()
            if not row:
                original = self._bot_profile(uid)
                if not original:
                    raise WebError('Войдите в игру.', 401)
                p = {**original, 'hero': original.get('hero', 'режиссер')}
                db.execute('INSERT INTO users VALUES(?,?,?)', (uid, str(original.get('nickname') or 'Игрок')[:32], json.dumps(p, ensure_ascii=False)))
            p = self._profile_json(db, uid)
            pack_id = secrets.token_urlsafe(18)
            db.execute('INSERT INTO promo_claims VALUES(?,?)', (canonical, uid))
            db.execute('INSERT INTO packs VALUES(?,?,?,?,?,?)', (pack_id, uid, target if promo.get('type') == 'set' else None, name, json.dumps(cards), int(immediate)))
            if immediate:
                self._grant_pack(db, uid, p, cards, target if promo.get('type') == 'set' else None)
        result = {'pack_id': pack_id, 'name': name, 'remaining': promo.get('limit', 1) - len(used) - 1}
        if immediate:
            result['collection'] = p['collection']
            result['sets'] = p.get('sets', [])
        return result

    def _grant_pack(self, db, uid, p, cards, set_id):
        p['collection'] = self.collection_counts(uid, p)
        for cid in cards:
            p['collection'][cid] = p['collection'].get(cid, 0) + 1
        if set_id and set_id not in p.get('sets', []):
            p.setdefault('sets', []).append(set_id)
        self._save_profile(db, uid, p)

    def open_pack(self, uid, pack_id):
        from web_service import WebError
        with self.transaction() as db:
            pack = db.execute('SELECT * FROM packs WHERE id=? AND uid=?', (pack_id, uid)).fetchone()
            if not pack:
                raise WebError('Пакетик не найден.', 404)
            cards = json.loads(pack['cards'])
            if not pack['opened']:
                p = self._profile_json(db, uid)
                self._grant_pack(db, uid, p, cards, pack['set_id'])
                db.execute('UPDATE packs SET opened=1 WHERE id=?', (pack_id,))
        # A lost response/retry returns the same rewards without granting twice.
        return {'id': pack_id, 'name': pack['name'], 'cards': [{'id': cid, **CARDS[cid], 'legendary': cid in LEGENDARY_CARD_IDS} for cid in cards]}
