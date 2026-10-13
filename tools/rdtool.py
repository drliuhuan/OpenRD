#!/usr/bin/env python3
"""OpenRD archaeology tool. Contains no Rich Diamond game data."""
import argparse, hashlib, json, pathlib, sys
SECTOR=2048

class BitReader:
    def __init__(self, data): self.data=data; self.pos=0; self.cur=0; self.left=0
    def bit(self):
        if not self.left:
            if self.pos >= len(self.data): raise EOFError('compressed bitstream ended')
            self.cur=self.data[self.pos]; self.pos+=1; self.left=8
        self.left-=1
        return (self.cur >> self.left) & 1
    def byte_bits(self):
        v=0
        for _ in range(8): v=(v<<1)|self.bit()
        return v

def _tree(br, depth=0):
    if depth > 512: raise ValueError('invalid coding tree')
    if br.bit():
        return None if br.bit() else br.byte_bits()  # None = EOF terminal
    # CC decoder stores the zero child at +8 and one child at +4.
    return (_tree(br, depth+1), _tree(br, depth+1))

def cc_decompress(data):
    """Decode Core Concepts' 0xCA static prefix-code wrapper."""
    if not data or data[0] != 0xCA: raise ValueError('not a 0xCA Core Concepts stream')
    br=BitReader(data[1:]); root=_tree(br); out=bytearray()
    while True:
        n=root
        while isinstance(n, tuple): n=n[br.bit()]
        if n is None: break
        out.append(n)
    return bytes(out)

def parse_lvs(raw):
    if raw[:4] != b'ST1\n': raise ValueError('unsupported LVS plaintext header')
    p=4
    def u16():
        nonlocal p
        if p+2>len(raw): raise ValueError('truncated LVS')
        v=int.from_bytes(raw[p:p+2],'little'); p+=2; return v
    def blob(n):
        nonlocal p
        if p+n>len(raw): raise ValueError('truncated LVS')
        v=raw[p:p+n]; p+=n; return v
    flags=u16(); base=blob(u16()).decode('latin1'); count=u16(); levels=[]
    for i in range(count):
        name=blob(u16()).decode('latin1')
        packed_len=u16(); packed=blob(packed_len); trailer=blob(14)
        levels.append({'index':i+1,'name':name,'packed_map_bytes':packed_len,
                       'trailer_hex':trailer.hex(), '_packed':packed})
    footer=raw[p:]
    return {'header':'ST1\\n','flags':flags,'base':base,'count':count,'levels':levels,
            'footer_bytes':len(footer),'footer_hex':footer.hex()}

def decode_packed_map(packed):
    """Decode WINPACK's row-oriented 128-row tile stream.

    0x02 ends a row, 0x01 ends the map, and 0x03..0x1f repeat the
    following tile byte that many times. Other bytes are literal tile IDs.
    Rows are right-trimmed by the original writer.
    """
    rows=[]; row=[]; p=0
    while p < len(packed):
        b=packed[p]; p+=1
        if b == 0x01:
            if row: raise ValueError('map terminator inside non-empty row')
            break
        if b == 0x02:
            rows.append(row); row=[]; continue
        if 0x03 <= b <= 0x1f:
            if p >= len(packed): raise ValueError('truncated map RLE run')
            tile=packed[p]; p+=1; row.extend([tile]*b)
        else:
            row.append(b)
    if len(rows) != 128:
        raise ValueError(f'expected 128 map rows, got {len(rows)}')
    return rows








def load_plain(path):
    d=path.read_bytes(); return cc_decompress(d) if d[:1]==b'\xca' else d










