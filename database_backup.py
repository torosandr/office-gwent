"""Private portable backups. DATABASE_URL stays in the environment, never in the file."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import time
from contextlib import closing

from database import Database

TABLES = {
    'users': ('uid', 'name', 'profile'),
    'sessions': ('token', 'uid', 'expires'),
    'rooms': ('code', 'p1', 'p2', 'phase', 'snapshot', 'version', 'awarded'),
    'membership': ('uid', 'code'),
    'actions': ('uid', 'request_id'),
    'promo_claims': ('code', 'uid'),
    'packs': ('id', 'uid', 'set_id', 'name', 'cards', 'opened'),
    'telegram_updates': ('update_id',),
}


def export(database, destination):
    with database.transaction() as db:
        tables = {name: [dict(row) for row in db.execute('SELECT * FROM ' + name).fetchall()]
                  for name in TABLES}
    payload = {'format': 1, 'created_at': int(time.time()), 'tables': tables}
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents overwriting an earlier recovery point.
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False)
    return sum(len(rows) for rows in tables.values())


def restore(service, source):
    data = json.loads(Path(source).read_text(encoding='utf-8'))
    return restore_payload(service, data)


def restore_payload(service, data):
    if data.get('format') != 1 or set(data.get('tables', {})) != set(TABLES):
        raise ValueError('Неизвестный формат резервной копии.')
    # Validate before writing. Unknown fields are never turned into SQL.
    for name, rows in data['tables'].items():
        if not isinstance(rows, list) or any(not isinstance(row, dict) or set(row) != set(TABLES[name]) for row in rows):
            raise ValueError('Некорректная таблица: ' + name)
    with service.transaction() as db:
        for name in TABLES:
            if db.execute('SELECT 1 FROM ' + name + ' LIMIT 1').fetchone():
                raise ValueError('Восстановление разрешено только в пустую базу. Текущие данные не изменены.')
        for name, columns in TABLES.items():
            sql = 'INSERT INTO ' + name + '(' + ','.join(columns) + ') VALUES(' + ','.join('?' for _ in columns) + ')'
            for row in data['tables'][name]:
                db.execute(sql, tuple(row[key] for key in columns))
        db.execute('CREATE TABLE IF NOT EXISTS storage_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('INSERT INTO storage_meta VALUES(?,?) ON CONFLICT(key) DO NOTHING', ('bot_seed_v1', '1'))


def import_sqlite(service, source):
    """Import an existing Mini App database without modifying its source file."""
    source = Path(source).resolve(strict=True)
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        tables = {name: [dict(row) for row in db.execute('SELECT * FROM ' + name)] if name in names else []
                  for name in TABLES}
    # Reuse validated, atomic restore rather than partially importing tables.
    with service.transaction() as db:
        restore_payload(service, {'format': 1, 'tables': tables})
        # SQLite had a separate bot file. Merge initial collections by max
        # because Mini App snapshots already include imported bot copies.
        db.execute('DELETE FROM storage_meta WHERE key=?', ('bot_seed_v1',))
        from cloud_storage import seed_profiles
        seed_profiles(service, merge_existing=True)


def main():
    parser = argparse.ArgumentParser(description='Резервная копия базы Офисного Гвинта')
    parser.add_argument('action', choices=('export', 'restore', 'import-sqlite'))
    parser.add_argument('file')
    args = parser.parse_args()
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise SystemExit('Задайте DATABASE_URL в окружении. Не передавайте пароль аргументом команды.')
    try:
        if args.action == 'export':
            count = export(Database('', url), args.file)
            print('Резервная копия сохранена. Записей:', count)
        else:
            from web_service import Service
            from config import FILES
            service = Service('', database_url=url, profiles_path=Path(__file__).parent / FILES['users'])
            (restore if args.action == 'restore' else import_sqlite)(service, args.file)
            print('Данные перенесены.')
    except Exception as error:
        # Connection errors may contain connection details: never log the DSN.
        raise SystemExit('Операция не выполнена (' + type(error).__name__ + '). Проверьте подключение и файл.') from None


if __name__ == '__main__':
    main()
