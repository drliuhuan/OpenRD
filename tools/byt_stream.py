"""Sequential CCIb10 reader derived from CCENG's 0x412Dxx dispatcher."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
import rdtool
from gin_tail import Reader, Unsupported

def object_record(data, pos):
    r=Reader(data,pos+1)
    first,second,word,byte,flags,w1,w2,graphic,last=struct.unpack('<BBHBBHHHB',r.take(13))
    record=dict(offset=pos,opcode=1,leading_bytes_raw=[first,second],
                tile_code=first,resource_id=graphic,
                parameter_raw=word,byte_raw=byte,flags_raw=flags,
                words_raw=[w1,w2],graphic_id_raw=graphic,last_byte_raw=last,commands=[])
    while True:
        begin=r.pos;sub=r.byte()
        if sub==1:break  # inner end is ONE, not the outer zero.
        command=dict(offset=begin,subcommand=sub)
        if sub==2:
            command['leading_words_raw']=r.words(2)
            command['bytes_raw']=list(r.take(2))
            command['trailing_words_raw']=r.words(2)
        elif sub==3:command['value_raw']=r.byte()
        elif sub==4:command['value_raw']=r.words(1)[0]
        elif sub in (5,7):command.update(r.string())
        elif sub==6:command['bytes_raw']=list(r.take(3))
        else:raise Unsupported(f'BYT object subcommand {sub} at {begin:#x}')
        command['next_offset']=r.pos;record['commands'].append(command)
    record['next_offset']=r.pos
    return record

def parse(data):
    if data[:6]!=b'CCIb10':raise ValueError('Expected CCIb10')
    pos=6;records=[];terminated=False;reason=None
    while pos<len(data):
        opcode=data[pos]
        try:
            if opcode==0:
                record=dict(offset=pos,opcode=0,next_offset=pos+1);terminated=True
            elif opcode==1:record=object_record(data,pos)
            elif opcode==2:
                # 0x413719: byte, u32 assembled from two words, byte
                # count word, three additional words, then exactly count bytes.
                r=Reader(data,pos+1);flag=r.byte();values=r.words(6)
                payload=r.take(values[2])
                record=dict(offset=pos,opcode=2,byte_raw=flag,words_raw=values,
                            payload_hex=payload.hex(),next_offset=r.pos)
            elif opcode in (3,4,5,6,7):
                count=4 if opcode==7 else 1
                r=Reader(data,pos+1)
                values=list(r.take(count))
                record=dict(offset=pos,opcode=opcode,bytes_raw=values,next_offset=r.pos)
            else:raise Unsupported(f'BYT opcode {opcode} at {pos:#x}')
        except Unsupported as exc:reason=str(exc);break
        records.append(record);pos=record['next_offset']
        if terminated:break
    return dict(decoded_sha256=hashlib.sha256(data).hexdigest(),decoded_bytes=len(data),
                stop_offset=pos,stop_opcode=data[pos] if pos<len(data) else None,
                stop_reason=reason,terminated=terminated,complete=terminated and pos==len(data),
                record_count=len(records),object_count=sum(x['opcode']==1 for x in records),records=records)

