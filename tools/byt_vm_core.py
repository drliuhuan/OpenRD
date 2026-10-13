"""Auditable VM core. Engine operations stop explicitly, never return fake values."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from byt_vm_prefix import prefix
from byt_events import consume, enqueue

class EngineStateUnavailable(ValueError):
    """A required native global value has not been explicitly supplied."""

def word(n):
    n &= 65535
    return n if n < 32768 else n - 65536

def xy(n):
    x,y = (n >> 4)&7, n&7
    return (-x if n&128 else x, -y if n&8 else y)

@dataclass
class Context:
    """Native shared operand context at 0x4620A0, separate from runtime objects."""
    stack: list = field(default_factory=list)
    last: tuple = (0,0)

@dataclass
class Core:
    code: bytes
    mask: int = 0
    call_capacity: int = 1
    position: tuple = (0,0)
    ip: int = 0
    fields: list = field(default_factory=lambda:[0,0,0,0])
    events: dict = field(default_factory=dict)
    context: Context = field(default_factory=Context)
    returns: list = field(default_factory=list)
    graphics: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    host: object = None
    disposed: bool = False

    @property
    def stack(self):return self.context.stack

    @property
    def last(self):return self.context.last

    @last.setter
    def last(self,value):self.context.last=value

    def __post_init__(self):
        parsed = prefix(self.code)
        if not parsed['complete']:raise ValueError('Incomplete instruction boundaries')
        self.instructions = {i['offset']:i for i in parsed['instructions']}

    def integer(self):
        if not self.stack:raise ValueError('VM stack underflow')
        kind,value = self.stack.pop()
        if kind != 0:raise ValueError('Expected integer stack operand')
        return value

    def push(self,n):self.stack.append((0,word(n)))

    def run(self,limit=10000):
        if self.disposed:return dict(reason='object already disposed',offset=self.ip)
        # 0x417552 clears live stack at every interpreter invocation.
        self.stack.clear()
        for _ in range(limit):
            if self.ip not in self.instructions:
                return dict(reason='invalid instruction pointer',offset=self.ip)
            i=self.instructions[self.ip];op=i['opcode'];operand=bytes.fromhex(i['operand_hex'])
            self.trace.append(dict(offset=self.ip,opcode=op,last=self.last,stack=list(self.stack)))
            self.ip=i['next_offset']
            try:
                if op==0:pass
                elif op in (1,2):self.push(int.from_bytes(operand,'little'))
                elif op==3:
                    if not self.stack:raise ValueError('Duplicate on empty stack')
                    self.stack.append(self.stack[-1])
                elif op in (6,7,8):
                    a=self.integer();self.push({6:lambda:not a,7:lambda:-a,8:lambda:~a}[op]())
                elif 9<=op<=20:
                    b=self.integer();a=self.integer()
                    self.push({9:lambda:a&b,10:lambda:a|b,11:lambda:a^b,
                               12:lambda:a+b,13:lambda:a-b,14:lambda:a*b,
                               15:lambda:a==b,16:lambda:a!=b,17:lambda:a>b,
                               18:lambda:a<b,19:lambda:a>=b,20:lambda:a<=b}[op]())
                elif op==21:self.stack.append(self.last)
                elif op==22:
                    if not self.stack:raise ValueError('Register store on empty stack')
                    self.last=self.stack.pop()
                elif op==23:self.stack.append((1,xy(operand[0])))
                elif op in (27,28):
                    count=self.integer() if op==28 else None
                    if not self.stack:raise ValueError('Missing direction coordinate')
                    kind,coordinate=self.stack.pop()
                    if kind!=1:raise ValueError('Expected direction coordinate')
                    if op==27:
                        self.push(coordinate[0]);self.push(coordinate[1])
                    else:
                        from byt_direction_sector import sector
                        self.push(sector(*coordinate,count))
                elif op==30 and self.host is not None:
                    start,end=xy(operand[0]),xy(operand[1])
                    position=tuple((self.position[j]+start[j])&255 for j in (0,1))
                    target=self.host.find(position)
                    if target is not None:
                        delta=tuple(end[j]-start[j] for j in (0,1))
                        self.host.move(target[1],delta,operand[2])
                elif op in (35,36) and self.host is not None:
                    state=self.integer() if op==35 else operand[1]
                    if op==35:
                        if not self.stack:raise ValueError('Missing overlay coordinate')
                        kind,coordinate=self.stack.pop()
                        if kind!=1:raise ValueError('Expected overlay coordinate')
                    else:coordinate=xy(operand[0])
                    position=tuple((self.position[j]+coordinate[j])&255 for j in (0,1))
                    if all(v<128 for v in position):self.host.set_overlay(position,state)
                elif op==44 and self.host is not None:
                    coordinate=xy(operand[0])
                    position=tuple((self.position[j]+coordinate[j])&255 for j in (0,1))
                    self.host.write_class(position,operand[1])
                elif op in (48,50) and self.host is not None:
                    coordinate=xy(operand[0])
                    position=tuple((self.position[j]+coordinate[j])&255 for j in (0,1))
                    self.host.write_parameter_bit(position,operand[1],op==48)
                elif op==55 and self.host is not None:
                    coordinate=xy(operand[0])
                    position=tuple((self.position[j]+coordinate[j])&255 for j in (0,1))
                    self.host.clear_graphic_layer_bit(position,operand[1])
                elif op in (32,38,39,46,72) and self.host is not None:
                    coordinate=xy(operand[0]) if op!=39 else None
                    if op==39:
                        if not self.stack:raise ValueError('Missing object-query coordinate')
                        kind,coordinate=self.stack.pop()
                        if kind!=1:raise ValueError('Expected object-query coordinate')
                    position=tuple((self.position[j]+coordinate[j])&255 for j in (0,1))
                    if op==72:self.host.defer(position,operand[1])
                    else:self.push(self.host.read(op,position,operand[1] if op==46 else None))
                elif op==51:
                    resource=self.integer()
                    if not self.stack:raise ValueError('Missing resource coordinate')
                    kind,coordinate=self.stack.pop()
                    if kind!=1:raise ValueError('Expected resource coordinate')
                    x,y=((self.position[j]+coordinate[j])&255 for j in (0,1))
                    if x<128 and y<128:self.graphics.append(dict(resource_id=resource,x=x,y=y,offset=i['offset']))
                elif op==75:self.push(consume(self.events))
                elif op in (57,58) and self.host is not None:
                    if op==57:self.host.adjust_collectibles(-1)
                    else:self.push(self.host.collectible_count)
                elif op in (63,64) and self.host is not None:
                    index=self.integer() if op==63 else operand[0]
                    self.push(self.host.get_value(index))
                elif op==65 and self.host is not None:
                    value=self.integer();index=self.integer()
                    self.host.set_value(index,value)
                elif op==68 and self.host is not None:self.push(self.host.get_setting(operand[0]))
                elif op in (59,61) and self.host is not None:
                    value=self.integer()
                    self.host.adjust_counter(-value if op==61 else value)
                elif op==74 and self.host is not None:
                    coordinate=xy(operand[0])
                    position=tuple((self.position[j]+coordinate[j])&255 for j in (0,1))
                    self.host.send_event(position,operand[1])
                elif op==66 and self.host is not None:self.host.set_value(operand[0],operand[1])
                elif op in (76,77,78,79) and self.host is not None:
                    direction=op-75
                    self.push(int(self.host.command_type() in (direction,direction+6)))
                elif op in (86,88,89,90) and self.host is not None:
                    self.host.audio_request(op,self.integer())
                elif op in (91,92,93,94):
                    event=self.integer() if op in (91,93) else operand[0]
                    bit=1<<((event-1)&31)
                    self.mask=(self.mask|bit) if op in (91,92) else (self.mask&~bit)
                    self.mask &= 0xffffffff
                elif op==95:self.events.pop(self.integer()&255,None)
                elif 96<=op<=99:self.push(self.fields[op-96])
                elif op in (100,102,104,106):self.fields[(op-100)//2]=self.integer()
                elif op in (101,103,105,107):self.fields[(op-101)//2]=operand[0]
                elif op==115 and self.host is not None:
                    self.stack.append((1,self.host.input_queue.take_target()))
                elif op==114 and self.host is not None:
                    player=self.host.player
                    coordinate=(0,0) if player is None else tuple(((player.position[j]-self.position[j]+128)&255)-128 for j in (0,1))
                    self.stack.append((1,coordinate))
                elif op==120 and self.host is not None:
                    mode=self.integer()
                    if not self.stack:raise ValueError('Missing target coordinate')
                    kind,coordinate=self.stack.pop()
                    if kind!=1:raise ValueError('Expected target coordinate')
                    self.host.expand_target(coordinate,mode)
                elif op==143 and self.host is not None:self.host.record_command()
                elif op in (139,141) and self.host is not None:
                    self.host.input_queue.remove_heads(self.host.input_queue.active,flagged_only=True,all_heads=op==141)
                elif op==136 and self.host is not None:
                    self.host.dispose_object(self)
                    return dict(reason='yield',state=None,disposed=True,offset=i['offset'],resume_offset=self.ip)
                elif op==138 and self.host is not None:
                    self.host.request_transition(operand[0],operand[1],self.integer())
                elif op in (124,125):
                    a=self.integer()
                    if bool(a)==(op==124):self.ip=i['jump_target']
                elif op==126:self.ip=i['jump_target']
                elif op==127:
                    if self.call_capacity==0:return dict(reason='call without return storage',offset=i['offset'])
                    if self.call_capacity==1:self.returns=[self.ip]
                    elif len(self.returns)<self.call_capacity:self.returns.append(self.ip)
                    self.ip=i['jump_target']
                elif op==128:
                    if self.returns:self.ip=self.returns.pop()
                    else:
                        self.ip=0
                        return dict(reason='return without saved address',offset=i['offset'])
                elif op in (129,130,131,133):
                    if op==129:self.ip=0
                    state={129:3 if self.events else None,130:2,131:3,133:3 if self.events else 4}[op]
                    return dict(reason='yield',state=state,offset=i['offset'],resume_offset=self.ip)
                elif op in (144,145,146,147):
                    a=self.integer() if op in (146,147) else self.last[1] if self.last[0]==0 else 0
                    equal=a==operand[0]
                    if equal==(op in (145,147)):self.ip=i['jump_target']
                else:
                    self.ip=i['offset']
                    return dict(reason='engine operation not implemented',opcode=op,offset=self.ip)
            except EngineStateUnavailable as exc:
                self.ip=i['offset']
                return dict(reason='engine state unavailable',detail=str(exc),offset=i['offset'])
            except ValueError as exc:
                return dict(reason='invalid stack operation',detail=str(exc),offset=i['offset'])
        return dict(reason='instruction budget exceeded',offset=self.ip)


