"""GIN opcode 38 map basis: 42B6BB reader -> 42D760 -> 42E5F0."""
from dataclasses import dataclass
from gin_graphics_state import signed


@dataclass(frozen=True)
class Projection:
    width: int
    height: int
    x_basis: tuple
    y_basis: tuple

    @classmethod
    def from_gin(cls, gin):
        records=[r for r in gin['records'] if r['opcode']==38]
        if len(records)!=1:
            raise ValueError('Expected exactly one map configuration')
        values=records[0]['values_raw']
        return cls(values[0],values[1],tuple(map(signed,values[2:4])),
                   tuple(map(signed,values[4:6])))

    def project(self, x, y):
        return tuple(signed(self.x_basis[j]*x+self.y_basis[j]*y) for j in (0,1))

    def place(self, instance, x, y, resource=None):
        # 4307F0 resets position without resetting action or script cursor.
        instance.position=self.project(x,y)
        if resource is not None:
            instance.resource=resource
