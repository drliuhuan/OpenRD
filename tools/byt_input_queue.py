"""Four native input slots: append, prepend and remove current head."""
from dataclasses import dataclass

@dataclass
class Command:
    kind:int
    x:int=0
    y:int=0
    flag:int=0

class InputQueue:
    def __init__(self):
        self.slots=[[] for _ in range(4)]
        self.active=0

    def head(self):
        return self.slots[self.active][0] if self.slots[self.active] else None

    def append(self,slot,command):
        if 0<=slot<4:self.slots[slot].append(command)

    def prepend(self,command):self.slots[self.active].insert(0,command)

    def pop(self):
        if self.head() is not None:return self.slots[self.active].pop(0)

    def remove_heads(self,slot,flagged_only=False,all_heads=False):
        if not 0<=slot<4:return []
        removed=[]
        queue=self.slots[slot]
        while queue:
            if flagged_only and not queue[0].flag:break
            removed.append(queue.pop(0))
            if not all_heads:break
        return removed

    def take_target(self):
        command=self.head()
        if command is None or command.kind!=5:return (0,0)
        self.pop()
        return (command.x&255,command.y&255)
