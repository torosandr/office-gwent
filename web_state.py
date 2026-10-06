"""JSON snapshots of the existing engine, including pending unit references."""
import random
from battle import Game
from player import Player
from unit import Unit


def dump_game(game):
    units = []
    by_identity = {}

    def unit_ref(unit):
        if id(unit) not in by_identity:
            by_identity[id(unit)] = len(units)
            units.append(dict(vars(unit)))
        return by_identity[id(unit)]

    players = {}
    for number, player in game.players.items():
        data = {k: v for k, v in vars(player).items() if k not in ('_game', 'board', 'pending')}
        data['board'] = [unit_ref(u) for u in player.board]
        data['pending'] = [{**{k: v for k, v in item.items() if k != 'unit'},
                            **({'unit_ref': unit_ref(item['unit'])} if item.get('unit') is not None else {})}
                           for item in player.pending]
        players[str(number)] = data
    return {'schema': 1, 'game': {k: v for k, v in vars(game).items() if k not in ('players', 'rng')},
            'players': players, 'units': units, 'rng': game.rng.getstate()}


def load_game(data):
    if data['schema'] != 1:
        raise ValueError('Unsupported game snapshot')
    game = Game.__new__(Game)
    game.__dict__.update(data['game'])
    def tuples(value):
        return tuple(tuples(x) for x in value) if isinstance(value, list) else value
    game.rng = random.Random()
    game.rng.setstate(tuples(data['rng']))
    units = []
    for index, attributes in enumerate(data['units']):
        unit = Unit.__new__(Unit)
        unit.__dict__.update(attributes)
        # Deterministic fallback keeps old snapshots stable until next save.
        unit.__dict__.setdefault('_visual_id', f'legacy-{index}')
        units.append(unit)
    game.players = {}
    for number, attributes in data['players'].items():
        player = Player.__new__(Player)
        player.__dict__.update({k: v for k, v in attributes.items() if k not in ('board', 'pending')})
        player._game = game
        player.board = [units[i] for i in attributes['board']]
        player.pending = [{**{k: v for k, v in item.items() if k != 'unit_ref'},
                           **({'unit': units[item['unit_ref']]} if 'unit_ref' in item else {})}
                          for item in attributes['pending']]
        game.players[int(number)] = player
    return game
