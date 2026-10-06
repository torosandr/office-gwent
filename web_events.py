"""Public sound events, committed atomically inside each room snapshot."""
import time
from cards import CARDS


def capture_effects(game):
    units = [u for p in game.players.values() for u in p.board]
    return {
        'units': [(u, u.hp, getattr(u, '_healed_total', 0)) for u in units],
        'stress': {n: p.stress for n, p in game.players.items()},
        'decks': {n: len(p.deck) for n, p in game.players.items()},
        'healed': getattr(game, '_healed_total', 0),
        'visual': {
            n: {
                'hero': (getattr(p, '_damaged_total', 0), getattr(p, '_healed_total', 0)),
                'units': [(u, getattr(u, '_damaged_total', 0), getattr(u, '_healed_total', 0),
                           getattr(u, '_blocked_total', 0)) for u in p.board],
                'hand': list(p.hand),
            } for n, p in game.players.items()
        },
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
    record_visuals(game, before, action, body, actor, now)


def record_visuals(game, before, action, body, actor, now):
    """Actual effects and stable public board references; no hidden card data."""
    old = before['visual']
    effects = []
    present = {u._visual_id for p in game.players.values() for u in p.board}
    previous = {u._visual_id for p in old.values() for u, *_ in p['units']}

    def ref(number, unit=None):
        return {'player': number, **({'unit': unit._visual_id} if unit else {'hero': True})}

    def effect(kind, target, amount=None):
        item = {'kind': kind, 'target': target}
        if amount is not None:
            item['amount'] = amount
        effects.append(item)

    for n, p in game.players.items():
        damaged, healed = old[n]['hero']
        for kind, amount in [('damage', getattr(p, '_damaged_total', 0)-damaged),
                             ('heal', getattr(p, '_healed_total', 0)-healed)]:
            if amount > 0:
                effect(kind, ref(n), amount)
        for u, damaged, healed, blocked in old[n]['units']:
            target = ref(n, u)
            for kind, amount in [('damage', getattr(u, '_damaged_total', 0)-damaged),
                                 ('heal', getattr(u, '_healed_total', 0)-healed)]:
                if amount > 0:
                    effect(kind, target, amount)
            if getattr(u, '_blocked_total', 0) > blocked:
                effect('block', target)
            if u._visual_id not in present:
                effect('death' if u.hp <= 0 or action == 'attack' else 'leave', target)
        for u in p.board:
            if u._visual_id not in previous:
                effect('enter', ref(n, u))

    source = ref(actor)
    target = None
    kind = action
    index = body.get('index')
    if action == 'attack' and type(index) is int and index < len(old[actor]['units']):
        source = ref(actor, old[actor]['units'][index][0])
        victim = body.get('target')
        if str(victim) == 'hero':
            target = ref(3-actor)
        elif str(victim).isdigit() and int(victim) < len(old[3-actor]['units']):
            target = ref(3-actor, old[3-actor]['units'][int(victim)][0])
    elif action in ('play', 'cast') and type(index) is int and index < len(old[actor]['hand']):
        source = {'player': actor, 'hand': index}
        card = CARDS[old[actor]['hand'][index]]
        kind = 'spell' if card.get('type') == 'spell' else 'play'
        victim = str(body.get('target', ''))
        own = card.get('status') in ('хил_цель', 'сокращение')
        owner = actor if own else 3-actor
        if victim in ('hero_self', 'hero_opp'):
            target = ref(owner)
        elif victim.isdigit() and int(victim) < len(old[owner]['units']):
            target = ref(owner, old[owner]['units'][int(victim)][0])

    event_id = getattr(game, '_visual_event_id', 0) + 1
    event = {'id': event_id, 'at': now, 'action': kind, 'actor': actor,
             'source': source, 'target': target, 'effects': effects,
             'turn': game.turn if action == 'end' and game.phase == 'active' else None,
             'winner': game.winner if game.phase == 'finished' else None}
    game._visual_events = (list(getattr(game, '_visual_events', [])) + [event])[-32:]
    game._visual_event_id = event_id
