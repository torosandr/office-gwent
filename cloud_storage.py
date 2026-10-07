"""Text bot profiles in the same transactional database as the Mini App."""
from copy import deepcopy
import json
from pathlib import Path
from storage import UserStore, DEFAULT_USER


def seed_profiles(service, merge_existing=False):
    """Import the checked-in bot seed once; never reset live accounts on restart."""
    with service.transaction() as db:
        db.execute('CREATE TABLE IF NOT EXISTS storage_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        if db.execute('SELECT 1 FROM storage_meta WHERE key=?', ('bot_seed_v1',)).fetchone():
            return
        path = Path(service.profiles_path) if service.profiles_path else None
        data = json.loads(path.read_text(encoding='utf-8')) if path and path.exists() else {}
        if not isinstance(data, dict):
            raise ValueError('Некорректный файл начальных профилей.')
        for uid, profile in data.items():
            if uid == '_version' or not isinstance(profile, dict):
                continue
            profile = {**deepcopy(DEFAULT_USER), **profile}
            if merge_existing:
                row = db.execute('SELECT profile FROM users WHERE uid=?', (str(uid),)).fetchone()
                if row:
                    current = json.loads(row['profile'])
                    collection = dict(current.get('collection', {}))
                    for cid, count in profile.get('collection', {}).items():
                        collection[cid] = max(collection.get(cid, 0), count)
                    current['collection'] = collection
                    current['wins'] = max(current.get('wins', 0), profile.get('wins', 0))
                    current['sets'] = list(dict.fromkeys(current.get('sets', []) + profile.get('sets', [])))
                    if profile.get('nickname'):
                        current['nickname'] = profile['nickname']
                    db.execute('UPDATE users SET name=?,profile=? WHERE uid=?',
                               (str(current.get('nickname') or 'Игрок')[:32], json.dumps(current, ensure_ascii=False), str(uid)))
            db.execute('INSERT INTO users(uid,name,profile) VALUES(?,?,?) ON CONFLICT(uid) DO NOTHING',
                       (str(uid), str(profile.get('nickname') or 'Игрок')[:32],
                        json.dumps(profile, ensure_ascii=False)))
        for code, promo in service.reward_catalog('codes').items():
            for claim in promo.get('used_by', []) if isinstance(promo, dict) else []:
                if isinstance(claim, dict) and claim.get('id') is not None:
                    db.execute('INSERT INTO promo_claims(code,uid) VALUES(?,?) '
                               'ON CONFLICT(code,uid) DO NOTHING',
                               (code.casefold(), str(claim['id'])))
        db.execute('INSERT INTO storage_meta VALUES(?,?)', ('bot_seed_v1', '1'))


def migrate_stepan(service):
    """Keep the newly legendary Stepan once, including in saved decks."""
    with service.transaction() as db:
        if db.execute('SELECT 1 FROM storage_meta WHERE key=?', ('legendary_stepan_v1',)).fetchone():
            return
        for row in db.execute('SELECT uid,profile FROM users').fetchall():
            profile = json.loads(row['profile'])
            changed = False
            if profile.get('collection', {}).get('степан', 0) > 1:
                profile['collection']['степан'] = 1
                changed = True
            deck = profile.get('deck', []) or []
            if deck.count('степан') > 1:
                seen = False
                clean = []
                for cid in deck:
                    if cid == 'степан':
                        if seen:
                            continue
                        seen = True
                    clean.append(cid)
                profile['deck'] = clean
                changed = True
            if changed:
                db.execute('UPDATE users SET profile=? WHERE uid=?', (json.dumps(profile, ensure_ascii=False), row['uid']))
        db.execute('INSERT INTO storage_meta VALUES(?,?)', ('legendary_stepan_v1', '1'))


class CloudUserStore(UserStore):
    def __init__(self, service):
        self.service = service
        self.reload()

    def _load_file(self):
        with self.service.connect() as db:
            rows = db.execute('SELECT uid,name,profile FROM users').fetchall()
        users = {}
        for row in rows:
            saved = json.loads(row['profile'])
            profile = {**deepcopy(DEFAULT_USER), **saved}
            # Accounts registered through the Mini App already have a name.
            if 'nickname' not in saved:
                profile['nickname'] = row['name']
                profile['state'] = 'menu'
            users[row['uid']] = profile
        return users

    def reload(self):
        count = super().reload()
        self.baseline = deepcopy(self.users)
        return count

    def persist(self):
        # Update only fields changed by the bot, preserving Mini App changes
        # made since the bot's in-memory snapshot (e.g. an opened pack).
        changes = {}
        with self.service.transaction() as db:
            for uid, profile in self.users.items():
                before = self.baseline.get(uid, {})
                changed = {key: value for key, value in profile.items()
                           if key not in before or value != before[key]}
                if not changed:
                    continue
                row = db.execute('SELECT name,profile FROM users WHERE uid=?', (uid,)).fetchone()
                current = json.loads(row['profile']) if row else deepcopy(DEFAULT_USER)
                current.update(changed)
                name = str(current.get('nickname') or (row['name'] if row else 'Игрок'))[:32]
                db.execute('INSERT INTO users(uid,name,profile) VALUES(?,?,?) '
                           'ON CONFLICT(uid) DO UPDATE SET name=excluded.name,profile=excluded.profile',
                           (uid, name, json.dumps(current, ensure_ascii=False)))
                changes[uid] = current
        # Preserve dictionary identity: handlers keep references to these users.
        for uid, current in changes.items():
            self.users[uid].update(current)
        self.baseline = deepcopy(self.users)
