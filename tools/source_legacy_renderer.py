"""Use real CCIg11 PCX rectangles in the shared indexed resource renderer."""
import struct
import zlib
from pathlib import Path
from source_formats import inspect_payload,pcx_png
from source_renderer import ResourceRenderer


def pcx_surface(data):
    png,info=pcx_png(inspect_payload(data)[0])
    pos=8;palette=None;compressed=[]
    while pos<len(png):
        size=int.from_bytes(png[pos:pos+4],'big');kind=png[pos+4:pos+8];raw=png[pos+8:pos+8+size];pos+=size+12
        if kind==b'PLTE':palette=raw
        if kind==b'IDAT':compressed.append(raw)
    rows=zlib.decompress(b''.join(compressed));w,h=info['width'],info['height']
    assert all(rows[y*(w+1)]==0 for y in range(h))
    return b''.join(rows[y*(w+1)+1:(y+1)*(w+1)] for y in range(h)),palette,w,h


def encode_crop(surface,width,rectangle,selector,keys):
    l,t,r,b=rectangle;w=max(0,r-l+1);h=max(0,b-t+1)
    if not (0<=l<=r+1<=width and 0<=t<=b+1<=len(surface)//width):raise ValueError('Legacy rectangle outside source PCX')
    if not w or not h:return b'',w,h
    payload=bytearray(h*2)
    for y in range(h):
        if len(payload)>65535:raise ValueError('Legacy sprite exceeds inline row address space')
        struct.pack_into('<H',payload,y*2,len(payload))
        row=surface[(t+y)*width+l:(t+y)*width+l+w];x=0
        while x<w:
            skip=selector!=2 and row[x] in keys
            end=x+1
            while end<w and end-x<63 and (selector!=2 and row[end] in keys)==skip:end+=1
            payload.append((64 if skip else 0)+(end-x))
            if not skip:payload.extend(row[x:end])
            x=end
        payload.append(0)
    return bytes(payload),w,h


class LegacyRenderer(ResourceRenderer):
    def __init__(self,gin,root):
        root=Path(root);bitmaps={};palette=None;records=[]
        for r in gin['records']:
            if r['opcode']!=4:continue
            matches=[p for p in (root/'raw').rglob('*') if p.is_file() and p.name.casefold()==Path(r['text']).name.casefold()]
            if len(matches)!=1:continue
            bitmaps[r['bitmap_id']]=(*pcx_surface(matches[0].read_bytes()),r['flags_raw'])
        for r in gin['records']:
            if r['opcode']==35:
                if r['bitmap_id'] not in bitmaps:raise ValueError('Missing source PCX bitmap')
                surface,pal,width,height,keys=bitmaps[r['bitmap_id']]
                if palette is None:palette=pal
                # Refuse incompatible palettes instead of silently recolouring.
                if pal!=palette:raise ValueError('Legacy map uses multiple distinct PCX palettes')
                payload,w,h=encode_crop(surface,width,r['rectangle'],r['selector_raw'],keys)
                l,t,_,_=r['rectangle'];ox,oy=r['origin_raw']
                records.append(dict(r,dimensions=[w,h],origin_raw=[(ox-l)&65535,(oy-t)&65535],
                                    flags_raw=[0,0,0],encoded_pixels_hex=payload.hex()))
            elif r['opcode'] not in (5,8):records.append(r)
        if palette is None:raise ValueError('No source PCX palette')
        records.append(dict(opcode=8,palette_rgb=list(palette)))
        super().__init__(dict(gin,format='CCIg12',records=records))
        self.source_gin=gin

    def components(self,rid,x=0,y=0,index=0,time=0,bindings=None,path=()):
        if len(path)>=64 or rid in path:raise ValueError('Legacy resource recursion cycle/depth')
        r=self.resources.get(rid,{})
        if r.get('subtype')==3:
            refs=r.get('resource_references',[])
            return self.components(refs[0],x,y,index,time,bindings,path+(rid,)) if refs else []
        if r.get('subtype')==7:
            refs=r.get('resource_references',[]);columns=r['parameters_raw'][0]
            rows=len(refs)//columns if columns>0 else 0
            if rows<=0:raise ValueError('Invalid legacy spatial selector')
            return self.components(refs[(y%rows)*columns+x%columns],x,y,index,time,bindings,path+(rid,))
        return super().components(rid,x,y,index,time,bindings,path)
