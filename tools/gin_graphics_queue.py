"""Native 429E00/429E60 queue and 420910 fixed-point step accumulator.

Input selector 0..20 is caller-supplied; its UI meaning is not yet established.
Rendering, native RNG and destructive instance cleanup remain outside this model.
"""
from dataclasses import dataclass
from gin_graphics_state import signed

INCREMENTS = (25,31,40,50,63,79,100,125,158,199,250,
              315,396,499,628,791,995,1253,1577,1986,2500)


@dataclass
class StepClock:
    remainder: int = 0

    def tick(self, selector):
        selector = max(0, min(20, selector))
        total = (self.remainder + INCREMENTS[selector]) & 0xffffffff
        total = total - 0x100000000 if total >= 0x80000000 else total
        quotient = total >> 8
        self.remainder = (total - (signed(quotient) << 8)) & 0xffffffff
        if self.remainder >= 0x80000000:
            self.remainder -= 0x100000000
        return quotient


class GraphicsQueue:
    def __init__(self):
        self.nodes = []
        self.cleanup_requests = []

    def enqueue(self, instance):
        if instance.cursor is not None or instance.archetype.entries:
            # Native performs no deduplication.
            self.nodes.insert(0, [instance, False])

    def request(self, instance, action):
        instance.request(action)
        self.enqueue(instance)

    def cancel(self, instance):
        for node in self.nodes:
            if node[0] is instance:
                node[1] = True
                return
        self.cleanup_requests.append(instance)

    def advance(self, steps, choose=None):
        results = []
        for index, (instance, cancelled) in enumerate(self.nodes):
            result = instance.advance(steps, choose=choose)
            results.append(result)
            if result['stopped']:
                self.nodes.pop(index)
                if cancelled:
                    self.cleanup_requests.append(instance)
                break  # 429E44..429E54 returns immediately after first removal.
        return results
