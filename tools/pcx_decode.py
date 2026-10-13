"""Decode the single-plane PCX atlases used during input preparation."""
import struct
import numpy as np

def decode_pcx(raw):
    if raw[:4] != bytes([10,5,1,8]) or raw[65] != 1:
        raise ValueError('Only version 5, RLE, 8-bit single-plane PCX is supported')
    if raw[-769] != 12: raise ValueError('Missing trailing PCX palette')
    xmin,ymin,xmax,ymax = struct.unpack_from('<4H', raw,4)
    width,height = xmax-xmin+1,ymax-ymin+1
    stride = struct.unpack_from('<H',raw,66)[0]
    if width<=0 or height<=0 or stride<width: raise ValueError('Invalid PCX dimensions')
    end = len(raw)-769; pos=128; pixels=bytearray()
    while pos<end:
        value=raw[pos]; pos+=1
        count=1
        if value>=192:
            count=value&63
            if not count or pos>=end: raise ValueError('Invalid PCX RLE run')
            value=raw[pos]; pos+=1
        pixels.extend(bytes([value])*count)
        if len(pixels)>stride*height+1: raise ValueError('PCX decoded overflow exceeds one byte')
    expected=stride*height
    if len(pixels)<expected: raise ValueError('PCX decoded pixels are truncated')
    overflow=bytes(pixels[expected:])
    indexes=np.frombuffer(bytes(pixels[:expected]),dtype=np.uint8).reshape(height,stride)[:,:width]
    palette=np.frombuffer(raw[-768:],dtype=np.uint8).reshape(256,3)
    return indexes,palette,{'width':width,'height':height,'stride':stride,
                             'decoded_extra_bytes':len(overflow),'extra_hex':overflow.hex()}
