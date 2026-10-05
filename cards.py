import json
import os

class BattleError(Exception):
    """Ошибка игрового действия (передаётся в UI как сообщение)."""
    pass


def load_cards(path='cards.json'):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


CARDS = load_cards()

def get(card_id):
    return CARDS.get(card_id, {})

def name(card_id):
    return get(card_id).get('name', card_id)


def copy_limit(card_id):
    from config import LEGENDARY_CARD_IDS
    return 1 if card_id in LEGENDARY_CARD_IDS else 2
