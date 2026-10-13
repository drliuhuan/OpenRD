"""GIN archetype cursor model, derived from CCENG 4309D0.

Explicit steps only: does not emulate renderer, timer or owner scheduling.
Random branches require an injected choice-index provider (not native RNG).
"""
from dataclasses import dataclass


def signed(value):
    value &= 65535
    return value - 65536 if value >= 32768 else value


class Archetype:
    def __init__(self, record):
        self.base = record['base_resource_id']
        self.entries = record['entries_raw']
        self.commands = [[] for _ in self.entries]
        for command in record['commands']:
            kind = command['subcommand']
            values = command['values_raw']
            source = values[0]
            if not 0 <= source < len(self.entries):
                raise ValueError('Archetype source entry out of range')
            if kind == 1:
                node = (0, values[1], None)
                self.commands[source].append(node)
            elif kind == 2:
                node = (1, values[2], values[1])
                self.commands[source].insert(0, node)
            elif kind == 3:
                node = (2, tuple(command['words_raw']), None)
                self.commands[source].insert(0, node)
            else:
                raise ValueError(f'Unknown archetype command {kind}')
            targets = node[1] if kind == 3 else [node[1]]
            if not 0 <= source < len(self.entries) or any(
                    not 0 <= target < len(self.entries) for target in targets):
                raise ValueError('Archetype entry reference out of range')


@dataclass
class Instance:
    archetype: Archetype
    cursor: int | None = None
    action: int = -1
    resource: int | None = None
    position: tuple = (0, 0)

    def __post_init__(self):
        if self.resource is None:
            self.resource = self.archetype.base

    def request(self, action):
        self.action = signed(action)

    def advance(self, steps, choose=None, limit=10000):
        steps = signed(steps)
        count = transitions = dx = dy = 0
        pending = None
        stopped = False

        def random_target(node):
            if choose is None:
                raise NotImplementedError('Native random branch requires explicit choice provider')
            index = choose(len(node[1]))
            if not 0 <= index < len(node[1]):
                raise ValueError('Choice index out of range')
            return node[1][index]

        while count < steps:
            transitions += 1
            if transitions > limit:
                raise RuntimeError('Graphical transition limit exceeded')
            if self.cursor is None:
                if not self.archetype.entries:
                    stopped = True
                    break
                self.cursor = 0
                initial = self.archetype.commands[0]
                if initial and initial[0][0] == 2:
                    self.cursor = random_target(initial[0])
            x, y, resource = self.archetype.entries[self.cursor]
            commands = self.archetype.commands[self.cursor]
            if not commands or commands[0][0] != 1:
                dx += x
                dy += y
                pending = resource
            if not commands:
                stopped = True
                break
            node = commands[0]
            if node[0] == 1:
                if self.action < 0:
                    stopped = True
                    break
                action, self.action = self.action, -1
                node = next((n for n in commands if n[0] != 1 or n[2] == action), None)
                if node is None:
                    self.cursor = None
                    stopped = True
                    break
                if node[0] == 1:
                    count -= 1
            self.cursor = random_target(node) if node[0] == 2 else node[1]
            count += 1
        self.position = (signed(self.position[0] + dx), signed(self.position[1] + dy))
        if pending is not None:
            self.resource = pending
        return dict(stopped=stopped, steps_consumed=count, transitions=transitions,
                    resource_id=self.resource, cursor=self.cursor,
                    position=list(self.position), pending_action=self.action)
