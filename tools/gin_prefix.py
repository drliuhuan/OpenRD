"""Sequential, bounded GIN prefix parser. Unknown opcodes stop explicitly."""
import argparse
import json
import struct
from pathlib import Path
import rdtool

def parse(data):
    if data[:6] not in (b'CCIg11', b'CCIg12'): raise ValueError('Unexpected GIN header')
    modern = data[:6] == b'CCIg12'
    pos=6;records=[];strings={}
    def take(n):
        nonlocal pos
        if pos+n>len(data):raise ValueError('Truncated GIN prefix')
        value=data[pos:pos+n];pos+=n;return value
    def words(n):return list(struct.unpack(f'<{n}H',take(n*2)))
    def string():
        if modern:
            size=words(1)[0]
            return dict(text=take(size).decode('latin1'))
        ref=words(1)[0]
        # This disc repeats inline bytes even for repeated IDs. Do not create
        # a cache from earlier literals; native lookup uses an external table.
        size=words(1)[0];text=take(size).decode('latin1')
        return dict(string_ref=ref,text=text)
    while pos<len(data):
        begin=pos;op=data[pos]
        if op not in (1,2,3,4,5,6,7,8,9,11,12,13,14,0x20,0x21,0x22,0x50,0x51,0x52,0x53,0x54,0x55,0x56,0x57) and not (modern and op in (0x6e,0x2c)):break
        pos+=1;record=dict(offset=begin,opcode=op)
        if op==0x6e:record['values_raw']=words(5)
        elif op in (1,2,3,6):record['values_raw']=words(4)
        elif op==4:
            record['bitmap_id']=words(1)[0];record.update(string())
            record['flags_raw']=list(take(3 if modern else 2))
        elif op==5 and modern:
            record['effect_indices']=list(take(256))
        elif op==5:
            bid,count=words(2);record.update(bitmap_id=bid,palette_rgb=list(take(count*3)))
        elif op==8 and modern:record['palette_rgb']=list(take(768))
        elif op in (7,8):record['values_raw']=words(1)
        elif op==9:record['values_raw']=words(4);record.update(string())
        elif op==11:record['values_raw']=words(3);record.update(string())
        elif op==12:record['ignored_bytes']=list(take(2));record['values_raw']=words(1);record.update(string())
        elif op==13:
            record['leading_bytes_raw']=list(take(2));record['values_raw']=words(4)
            record['flags_raw']=list(take(9));record['trailing_words_raw']=words(4)
            record['last_byte_raw']=take(1)[0]
        elif op==14:record['units']=words(1)[0];record.update(string())
        elif op==0x2c:record['collection_id']=words(1)[0];record.update(string())
        elif op==0x20:record['values_raw']=words(1)
        elif op==0x21:record['values_raw']=words(4);record['flags_raw']=list(take(2))
        elif op==0x22:record['values_raw']=words(4)
        elif op==0x50:record['values_raw']=words(4);record['flags_raw']=list(take(2))
        elif op in (0x51,0x54):record['values_raw']=words(1)
        elif op in (0x52,0x53,0x56):record['values_raw']=list(take(3))
        elif op==0x55 and modern:
            key=list(take(3));record.update(string_ref=int.from_bytes(bytes(key),'big'),string_key=key)
        elif op==0x55:record.update(string())
        elif op==0x57:record['values_raw']=words(9)
        record['next_offset']=pos;records.append(record)
    return dict(scope='sequential prefix from header; incomplete',stop_offset=pos,
                stop_opcode=data[pos] if pos<len(data) else None,records=records)

