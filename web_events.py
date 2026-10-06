"""Public sound events, committed atomically inside each room snapshot."""
import time


def capture_effects(game):
    units = [u for p in game.players.values() for u in p.board]
    return {
        'units': [(u, u.hp, getattr(u, '_healed_total', 0)) for u in units],
        'stress': {n: p.stress for n, p in game.players.items()},
        'decks': {n: len(p.deck) for n, p in game.players.items()},
        'healed': getattr(game, '_healed_total', 0),
    }


def record_effects(game, before, action, body, actor):
    """Only harmless sound kinds and player numbers are public, never card IDs."""
    events = list(getattr(game, '_web_events', []))
    counter = getattr(game, '_web_event_id', 0)
    emitted = set()
    now = time.time()

    def emit(kind, player=None):
        nonlocal counter
        key = (kind, player)
        if key in emitted:
            return
        emitted.add(key)
        counter += 1
        events.append({'id': counter, 'kind': kind, 'player': player, 'at': now})

    if action == 'attack':
        emit('attack_hero' if str(body.get('target')) == 'hero' else 'attack_unit')
    elif action in ('play', 'cast'):
        emit('card')
    elif action == 'hero':
        emit('hero')

    hero_damaged = any(p.stress < before['stress'][n] for n, p in game.players.items())
    unit_damaged = any(u.hp < hp for u, hp, _ in before['units'])
    if action != 'attack':
        if hero_damaged:
            emit('spell_hero')
        if unit_damaged:
            emit('spell_unit')
    if (getattr(game, '_healed_total', 0) > before['healed']
            or any(getattr(u, '_healed_total', 0) > healed for u, _, healed in before['units'])):
        emit('heal')
    if any(u.hp <= 0 < hp for u, hp, _ in before['units']):
        emit('death')
    for n, p in game.players.items():
        if len(p.deck) < before['decks'][n]:
            emit('draw', n)
    if game.phase == 'finished':
        emit('result', game.winner)
    elif action == 'end':
        emit('turn', game.turn)
    game._web_events = events[-64:]
    game._web_event_id = counter
