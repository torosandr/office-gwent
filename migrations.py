"""
Система миграций данных пользователей.

Файл данных хранит поле `_version`. При загрузке текущая версия сравнивается
со SCHEMA_VERSION, и к файлу по очереди применяются миграции `v1 -> v2 -> ...`.
Перед каждым преобразованием делается резервная копия в config.BACKUP_DIR,
чтобы ошибка миграции не уничтожила данные.

Как добавлять новое поле/структуру:
1. Увеличь SCHEMA_VERSION в config.py на 1.
2. Добавь функцию MIGRATIONS[новый_номер], которая принимает dict данных
   и возвращает его же, приведённый к новому виду.
"""

import os
import json
import shutil
import time
from copy import deepcopy
from json_io import atomic_write_json
from config import BACKUP_DIR, SCHEMA_VERSION

# Миграции по номеру версии: {номер_версии: функция(data) -> data}
# Функция с ключом N приводит данные из версии (N-1) к версии N.
MIGRATIONS = {
    # v1 -> v2: профили могли не иметь field 'wins'
    2: lambda data: _migrate_v2(data),
    # v2 -> v3: добавлены монеты (coins)
    3: lambda data: _migrate_v3(data),
}


def _migrate_v3(data):
    """v3: у каждого профиля появляется монета (coins) и выбранный герой."""
    for uid in data:
        prof = data[uid]
        if not isinstance(prof, dict):
            continue
        prof.setdefault('coins', 100)
        prof.setdefault('hero', 'режиссер')
    return data


def _migrate_v2(data):
    """Изначальная миграция: гарантировать наличие базовых полей у каждого профиля."""
    default = {"nickname": "", "sets": [], "collection": {}, "state": "start", "wins": 0}
    for uid in data:
        prof = data[uid]
        # в early-версии структура была {nickname:...}, могли быть без wins
        if not isinstance(prof, dict):
            data[uid] = deepcopy(default)
            continue
        for k, v in default.items():
            if k not in prof:
                prof[k] = deepcopy(v)
    return data


def _read_version(data):
    """Версия схемы: либо поле _version, либо 1 для старых файлов без него."""
    if isinstance(data, dict) and "_version" in data:
        try:
            return int(data["_version"])
        except (TypeError, ValueError):
            return 1
    return 1


def _backup(path):
    if not os.path.exists(path):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = os.path.basename(path)
    name, ext = os.path.splitext(base)
    dest = os.path.join(BACKUP_DIR, f"{name}_{stamp}{ext}")
    try:
        shutil.copy2(path, dest)
    except OSError as e:
        print(f"Предупреждение: не удалось сделать бэкап {path}: {e}")


def migrate_if_needed(path):
    """
    Читает файл, при необходимости мигрирует его до SCHEMA_VERSION и записывает.
    Возвращает мигрированный dict данных. Возвращает {} если файла нет.
    """
    if not os.path.exists(path):
        return {}

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    version = _read_version(data)
    if version >= SCHEMA_VERSION:
        # уже актуально
        return data

    # чистим служебное поле, работаем только с профилями
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if k != "_version"}

    changed = False
    while version < SCHEMA_VERSION:
        next_v = version + 1
        fn = MIGRATIONS.get(next_v)
        if fn is None:
            # нет миграции — просто поднимаем версию (поля добиваются в store.get)
            data = data
        else:
            _backup(path)  # бэкап перед изменением данных
            data = fn(data)
            changed = True
        version = next_v

    data["_version"] = SCHEMA_VERSION
    if changed:
        atomic_write_json(path, data)
    return data
