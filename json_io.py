"""Запись JSON без повреждения предыдущей версии при ошибке."""
import json
import os
import tempfile


def atomic_write_json(path, data):
    path = os.path.abspath(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=os.path.dirname(path),
            prefix='.' + os.path.basename(path) + '.', suffix='.tmp', delete=False,
        ) as stream:
            temporary = stream.name
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
