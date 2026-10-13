"""4301030 overlay-group selection; native timer/frame advancement pending."""
from dataclasses import dataclass
from gin_graphics_state import signed


@dataclass
class Overlay:
    groups: dict
    state: int = 0
    frame: int = 0
    selected: int | None = None

    def select(self,state):
        state=signed(state)
        if state==self.state:return False
        self.state=state
        self.frame=0
        previous=self.selected
        self.selected=state if state in self.groups else None
        return previous!=self.selected

    def advance(self,steps):
        if self.selected is None:return
        count=len(self.groups[self.selected])
        if count<2:return
        frame=signed(self.frame+signed(steps))
        # Native only subtracts while >= count; negative indices are unsafe.
        if frame<0:raise ValueError('Native overlay frame index would be negative')
        self.frame=frame%count

    @property
    def resource(self):
        return self.groups[self.selected][self.frame] if self.selected is not None else None
