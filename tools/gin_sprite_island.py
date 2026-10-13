"""Parse a bounded GIN island of 0x23/24/25/27/2A.

Not a whole-stream parser: entry offset is supplied explicitly. Refuse unknown
commands and invalid rectangles; report the stopping boundary without guessing.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
import rdtool

def parse(data, start, bitmap=35, width=2256, height=2266):
    pos = start
    records = []
    sprites = {}
    stop_reason = None
    terminated = False
    while pos < len(data):
        begin = pos
        if data[pos] == 0:
            records.append(dict(offset=pos,opcode=0,next_offset=pos+1))
            pos+=1
            terminated=True
            break
        if data[pos] == 0x43:
            # 0x4355C3..0x435934: eight little-endian words.
            if pos+17>len(data):raise ValueError('Truncated final script configuration')
            record=dict(offset=pos,opcode=0x43,values_raw=list(struct.unpack_from('<8H',data,pos+1)))
            pos+=17
        elif data[pos] == 0x23 and data[:6] == b'CCIg12':
            if pos+16>len(data):raise ValueError('Truncated inline sprite')
            sid,f1,f2,f3,w,h,ox,oy,size=struct.unpack_from('<H3B5H',data,pos+1)
            if w>4096 or h>4096 or pos+16+size>len(data):raise ValueError('Invalid inline sprite bounds')
            if sid in sprites:raise ValueError('Duplicate sprite')
            record=dict(offset=pos,opcode=35,sprite_id=sid,flags_raw=[f1,f2,f3],
                        dimensions=[w,h],origin_raw=[ox,oy],encoded_pixels_hex=data[pos+16:pos+16+size].hex(),
                        empty_rectangle=w==0 or h==0)
            sprites[sid]=record
            pos+=16+size
        elif data[pos] == 0x23:
            if pos + 21 > len(data): raise ValueError('Truncated sprite')
            sid,kind,bid,left,top,right,bottom,ox,oy,flag,selector = struct.unpack_from('<9H2B',data,pos+1)
            if (bitmap is not None and bid != bitmap) or not (0 <= left <= right+1 <= width and 0 <= top <= bottom+1 <= height):
                break
            if sid in sprites: raise ValueError('Duplicate sprite in island')
            record = dict(offset=pos,opcode=35,sprite_id=sid,kind_raw=kind,
                          bitmap_id=bid,rectangle=[left,top,right,bottom],
                          origin_raw=[ox,oy],flag_raw=flag,selector_raw=selector)
            record['empty_rectangle'] = left == right+1 or top == bottom+1
            sprites[sid] = record
            pos += 21
        elif data[pos] == 0x24:
            if pos + 6 > len(data): raise ValueError('Truncated frame header')
            rid,subtype,count = struct.unpack_from('<HBH',data,pos+1)
            if data[:6]==b'CCIg12' and subtype in (10,11,12,14):
                if subtype==11:
                    if count>=32768 or pos+6+2*count>len(data):raise ValueError('Invalid new resource list')
                    refs=list(struct.unpack_from(f'<{count}H',data,pos+6))
                    record=dict(offset=pos,opcode=36,resource_id=rid,subtype=subtype,resource_references=refs)
                    pos+=6+count*2
                else:
                    n=3 if subtype==10 else 2
                    if pos+4+2*n>len(data):raise ValueError('Truncated new resource')
                    values=list(struct.unpack_from(f'<{n}H',data,pos+4))
                    refs=values if subtype==14 else values[1:2] if subtype==12 else values[:1]
                    record=dict(offset=pos,opcode=36,resource_id=rid,subtype=subtype,parameters_raw=values,resource_references=refs)
                    pos+=4+2*n
                record['next_offset']=pos;records.append(record);continue
            if subtype == 2:
                if pos+8>len(data): raise ValueError('Truncated subtype 2')
                base,sid=struct.unpack_from('<2H',data,pos+4)
                record=dict(offset=pos,opcode=36,resource_id=rid,subtype=2,
                            base_resource_id=base,sprite_reference=sid)
                pos+=8
                record['next_offset']=pos
                records.append(record)
                continue
            if subtype in (3,4,5,7,8):
                words=1 if subtype==4 else 2
                if pos+4+words*2>len(data): raise ValueError('Truncated list header')
                header=list(struct.unpack_from(f'<{words}H',data,pos+4))
                count=header[-1]; payload=pos+4+words*2
                if count >= 32768: raise ValueError('Negative signed resource count')
                if payload+count*2>len(data): raise ValueError('Truncated list')
                record=dict(offset=pos,opcode=36,resource_id=rid,subtype=subtype,
                            parameters_raw=header[:-1],resource_references=list(
                                struct.unpack_from(f'<{count}H',data,payload)))
                pos=payload+count*2
                record['next_offset']=pos
                records.append(record)
                continue
            if subtype == 6:
                if pos + 16 > len(data): raise ValueError('Truncated subtype 6 header')
                base,p1,p2,p3,p4,count=struct.unpack_from('<6H',data,pos+4)
                if count >= 32768: raise ValueError('Negative signed resource count')
                if pos + 16 + count*2 > len(data): raise ValueError('Truncated resource references')
                refs=list(struct.unpack_from(f'<{count}H',data,pos+16))
                record=dict(offset=pos,opcode=36,resource_id=rid,subtype=6,
                            base_resource_id=base,parameters_raw=[p1,p2,p3,p4],
                            resource_references=refs)
                pos += 16 + count*2
                record['next_offset']=pos
                records.append(record)
                continue
            if subtype != 1: break
            if pos + 6 + count*6 > len(data): raise ValueError('Truncated frames')
            frames = []
            for index in range(count):
                sid,x,y = struct.unpack_from('<3H',data,pos+6+index*6)
                frames.append(dict(sprite_id=sid,offset_raw=[x,y]))
            record = dict(offset=pos,opcode=36,resource_id=rid,subtype=1,frames=frames)
            pos += 6 + count*6
        elif data[pos] == 0x27:
            if pos + 7 > len(data): raise ValueError('Truncated link header')
            target,base,count = struct.unpack_from('<3H',data,pos+1)
            if count >= 32768: raise ValueError('Negative signed link count')
            stride=2 if data[:6]==b'CCIg12' else 6
            if pos + 7 + count*stride > len(data): raise ValueError('Truncated links')
            links=[]
            for index in range(count):
                values=struct.unpack_from('<H' if stride==2 else '<3H',data,pos+7+index*stride)
                links.append(dict(resource_id=values[0],ignored_words=list(values[1:])))
            record=dict(offset=pos,opcode=39,target_resource_id=target,
                        base_resource_id=base,links=links)
            pos += 7 + count*stride
        elif data[pos]==0x42:
            from gin_tail import script,Unsupported
            try:record=script(data,pos)
            except Unsupported as exc:
                stop_reason=str(exc)
                break
            pos=record['next_offset']
        elif data[pos]==45 and data[:6]==b'CCIg12':
            if pos+7>len(data):raise ValueError('Truncated collection binding')
            record=dict(offset=pos,opcode=45,values_raw=list(struct.unpack_from('<3H',data,pos+1)))
            pos+=7
        elif data[pos]==4 and data[:6]==b'CCIg12':
            if pos+5>len(data):raise ValueError('Truncated bitmap filename')
            bid,size=struct.unpack_from('<2H',data,pos+1)
            if pos+8+size>len(data):raise ValueError('Truncated bitmap record')
            record=dict(offset=pos,opcode=4,bitmap_id=bid,text=data[pos+5:pos+5+size].decode('latin1'),flags_raw=list(data[pos+5+size:pos+8+size]))
            pos+=8+size
        elif data[pos] in (0x40,0x41):
            opcode=data[pos];n=2 if opcode==0x40 else 0
            if pos+1+n>len(data): raise ValueError('Truncated script configuration')
            record=dict(offset=pos,opcode=opcode,values_raw=list(
                struct.unpack_from('<H',data,pos+1)) if n else [])
            pos+=1+n
        elif data[pos] == 0x26:
            if pos+3>len(data): raise ValueError('Truncated attached component')
            subtype=struct.unpack_from('<H',data,pos+1)[0]
            if subtype==4:
                if pos+25>len(data): raise ValueError('Truncated subtype 4 component')
                values=list(struct.unpack_from('<11H',data,pos+3)); pos+=25
                commands=[]; refs=[]
                def read_words(n):
                    nonlocal pos
                    if pos+n*2>len(data): raise ValueError('Truncated component words')
                    result=list(struct.unpack_from(f'<{n}H',data,pos));pos+=n*2
                    return result
                def read_expression(depth=0):
                    nonlocal pos
                    if depth>128 or pos>=len(data): raise ValueError('Invalid component expression')
                    kind=data[pos];pos+=1
                    node=dict(kind_raw=kind)
                    if kind<10:
                        node['resource_id']=read_words(1)[0];refs.append(node['resource_id'])
                        if kind: node['children']=[read_expression(depth+1),read_expression(depth+1)]
                    return node
                while True:
                    if pos>=len(data): raise ValueError('Missing component terminator')
                    sub=data[pos];pos+=1
                    if sub==0: break
                    if sub==1:
                        if pos>=len(data): raise ValueError('Missing component kind')
                        kind=data[pos];pos+=1
                        command=dict(subcommand=sub,kind_raw=kind)
                        if kind<10:
                            command['resource_id']=read_words(1)[0];refs.append(command['resource_id'])
                            if kind: command['expressions']=[read_expression(),read_expression()]
                    elif sub==2:
                        vals=read_words(2);command=dict(subcommand=sub,values_raw=vals);refs.append(vals[1])
                    elif sub in (3,4):
                        vals=read_words(1+(16 if sub==3 else 47))
                        command=dict(subcommand=sub,values_raw=vals);refs.extend(v for v in vals[1:] if v)
                    else: raise ValueError(f'Unsupported component subcommand {sub}')
                    commands.append(command)
                record=dict(offset=begin,opcode=38,subtype=4,values_raw=values,
                            commands=commands,resource_references=refs)
                record['next_offset']=pos;records.append(record);continue
            words={1:5,2:1,3:3,5:1}.get(subtype) if data[:6]==b'CCIg12' else {1:5,2:1,3:3}.get(subtype)
            if words is None: break
            if pos+3+words*2>len(data): raise ValueError('Truncated component payload')
            values=list(struct.unpack_from(f'<{words}H',data,pos+3))
            record=dict(offset=pos,opcode=38,subtype=subtype,values_raw=values)
            if subtype==2: record['resource_references']=values
            pos+=3+words*2
        elif data[pos] == 0x2A:
            if pos+7>len(data): raise ValueError('Truncated object update')
            oid,parameter,count=struct.unpack_from('<3H',data,pos+1)
            if count>=32768 or pos+7+count*2>len(data): raise ValueError('Invalid update list')
            record=dict(offset=pos,opcode=42,object_id=oid,parameter_raw=parameter,
                        resource_references=list(struct.unpack_from(f'<{count}H',data,pos+7)))
            pos+=7+count*2
        elif data[pos] == 0x25:
            if pos+7>len(data): raise ValueError('Truncated object header')
            oid,count,base=struct.unpack_from('<3H',data,pos+1)
            if count>=32768: raise ValueError('Negative signed object count')
            if pos+7+count*6>len(data): raise ValueError('Truncated object entries')
            entries=[list(struct.unpack_from('<3H',data,pos+7+i*6)) for i in range(count)]
            pos+=7+count*6
            commands=[]
            while True:
                if pos>=len(data): raise ValueError('Missing object terminator')
                sub=data[pos]; pos+=1
                if sub==0: break
                if sub not in (1,2,3) and not (data[:6]==b'CCIg12' and sub==4): raise ValueError(f'Unsupported object subcommand {sub} at {pos-1:#x}')
                words=4 if sub==4 else 3 if sub==2 else 2
                if pos+words*2>len(data): raise ValueError('Truncated object subcommand')
                values=list(struct.unpack_from(f'<{words}H',data,pos));pos+=words*2
                command=dict(subcommand=sub,values_raw=values)
                if sub==3:
                    n=values[1]
                    if n>=32768 or pos+n*2>len(data): raise ValueError('Invalid object word list')
                    command['words_raw']=list(struct.unpack_from(f'<{n}H',data,pos));pos+=n*2
                commands.append(command)
            record=dict(offset=begin,opcode=37,object_id=oid,base_resource_id=base,
                        entries_raw=entries,commands=commands,
                        resource_references=[e[2] for e in entries if e[2]])
        else:
            break
        record['next_offset'] = pos
        records.append(record)
        if pos <= begin: raise AssertionError('No progress')
    resources={r['resource_id'] for r in records if r['opcode']==36}
    references=[]
    script_sprite_refs=[]
    for record in records:
        panel=record.get('text_panel',{})
        script_sprite_refs.extend(x for x in panel.get('sprite_references',[]) if x)
        script_sprite_refs.extend(e['sprite_id'] for e in panel.get('entries',[]) if e['sprite_id'])
        references.extend(record.get('resource_references',[]))
        if 'base_resource_id' in record: references.append(record['base_resource_id'])
        if record['opcode']==39:
            references.append(record['target_resource_id'])
            references.extend(link['resource_id'] for link in record['links'])
    return dict(scope='explicit-entry island; not full GIN',
                decoded_sha256=hashlib.sha256(data).hexdigest(),start_offset=start,
                stop_offset=pos,stop_opcode=data[pos] if pos<len(data) else None,
                stop_reason=stop_reason,
                terminated=terminated,trailing_bytes=len(data)-pos if terminated else None,
                script_count=sum(r['opcode']==0x42 for r in records),
                script_sprite_reference_count=len(script_sprite_refs),
                script_sprite_ids_outside_island=sorted(set(script_sprite_refs)-set(sprites)),
                record_count=len(records),sprite_count=len(sprites),
                resource_count=len(resources),
                object_count=sum(r['opcode']==37 for r in records),
                empty_sprite_ids=[sid for sid,r in sprites.items() if r['empty_rectangle']],
                resource_reference_count=len(references),
                sprite_ids_outside_island=sorted(({f['sprite_id'] for r in records
                    for f in r.get('frames',[])} | {r['sprite_reference'] for r in records
                    if 'sprite_reference' in r}) - set(sprites)),
                resource_ids_outside_island=sorted(set(references)-resources),records=records)

