"""Bounded IMC v1 structural parser; no native timing or theme selection claims."""
import struct


def parse(data):
    if len(data)>64*1024*1024: raise ValueError('IMC exceeds 64 MiB')
    pos=0
    def take(n):
        nonlocal pos
        if n<0 or pos+n>len(data): raise ValueError(f'Truncated IMC at {pos}')
        result=data[pos:pos+n];pos+=n;return result
    def byte():return take(1)[0]
    def word():return struct.unpack('<H',take(2))[0]
    def reference():return dict(scope_raw=byte(),id=word())
    def tree(depth=0):
        if depth>64:raise ValueError('IMC expression exceeds depth 64')
        kind=byte()
        if kind==0:return dict(kind=0,resource_id=word())
        if kind!=1:raise ValueError('Unknown IMC expression kind')
        delta,parameter=byte(),byte()
        return dict(kind=1,delta_raw=delta,parameter_raw=parameter,left=tree(depth+1),right=tree(depth+1))
    if take(3)!=b'i\x0ff' or byte()!=1:raise ValueError('Unsupported IMC header/version')
    header_raw=byte();name=take(byte()).decode('latin1');separator_raw=byte()
    records=[]
    while pos<len(data):
        if len(records)>=100000:raise ValueError('IMC exceeds 100000 records')
        start=pos;op=byte();r=dict(offset=start,opcode=op)
        if op==0:
            r['next_offset']=pos;records.append(r)
            if pos!=len(data):raise ValueError('Trailing bytes after IMC terminator')
            return dict(format='IMC1',group_name=name,header_raw=header_raw,separator_raw=separator_raw,
                        records=records,terminated=True,consumed=pos,
                        scope='Structural IMC commands; explicit references, no runtime selection')
        if op==2:
            sid=word();flags=[byte(),byte(),byte()];w,h,ox,oy,size=[word() for _ in range(5)]
            if w>4096 or h>4096:raise ValueError('IMC sprite dimensions exceed 4096')
            r.update(sprite_id=sid,flags_raw=flags,shade_slot=flags[2],dimensions=[w,h],origin_raw=[ox,oy],encoded_pixels_hex=take(size).hex())
            from source_pixels import inspect
            r['pixels']=inspect(bytes.fromhex(r['encoded_pixels_hex']),w,h)
        elif op==3:
            r['resource_id']=word();count=byte()
            r['components']=[dict(reference=reference(),offset_raw=[word(),word()]) for _ in range(count)]
        elif op in (4,17):
            r.update(resource_id=word(),references=[reference(),reference()])
        elif op in (6,16):
            r['resource_id']=word();count=byte();r['references']=[reference() for _ in range(count)]
        elif op in (7,8,9):
            r['resource_id']=word();count=byte();r['parameter_raw']=byte();r['references']=[reference() for _ in range(count)]
        elif op==11:
            r['resource_id']=word();count=byte();r['parameters_raw']=[word(),word(),byte(),word()]
            r['base']=reference();r['references']=[reference() for _ in range(count)]
        elif op==12:
            r['resource_id']=word();r['expression']=tree()
        elif op in (13,20):
            r['values_raw']=[word(),word()]
        elif op==14:
            r['values_raw']=[word(),word(),word(),word()];r['text']=take(byte()).decode('latin1')
        elif op==18:r['value_raw']=word()
        elif op==19:
            r.update(entry_id=word(),reference=reference(),offset_raw=[word(),word()],control_raw=byte(),next_raw=word())
        else:raise ValueError(f'Unsupported IMC command {op} at {start}')
        r['next_offset']=pos;records.append(r)
    raise ValueError('Missing IMC terminator')
