"""Prepare the verified baseline from a read-only ISO or installed game folder."""
import argparse
import hashlib
import io
import json
import struct
from pathlib import Path
import rdtool
import gin_stream
import byt_stream
from inspect_iso import inspect
from import_source import save

ROOT=Path(__file__).resolve().parent.parent
ENGINE_SHA='b967fdda363cf152a04c8c971c838583115d06837eea45c3a4b87c022d7ebe4d'

class BaselineInput:
    """Same payload reader for disc entries and loose installed files."""
    def __init__(self,source):
        self.source=Path(source).resolve()
        if self.source.is_dir():
            self.kind='game-folder'
            self.entries={p.name.upper():p for p in self.source.iterdir() if p.is_file()}
        else:
            self.kind='iso'
            self.entries={e['path'].upper():e for e in inspect(self.source)['files']}

    def read(self,name):
        entry=self.entries[name.upper()]
        if self.kind=='game-folder':return entry.read_bytes()
        with self.source.open('rb') as stream:
            stream.seek(entry['offset']);raw=stream.read(entry['size'])
        if len(raw)!=entry['size']:raise ValueError('Truncated ISO entry')
        return raw

    def is_baseline(self):
        required={'CCENG.EXE','RICHDIMD.GIN','RICHDIMD.BYT','ICONS.PCX'}
        return required<=set(self.entries) and bool({'RICHDIMD.LVS','DEMO.LVS'}&set(self.entries)) and hashlib.sha256(self.read('CCENG.EXE')).hexdigest()==ENGINE_SHA

    @staticmethod
    def plain(raw):
        return rdtool.cc_decompress(raw) if raw[:1]==b'\xca' else raw

def can_prepare(source):
    try:return BaselineInput(source).is_baseline()
    except (ValueError,KeyError,OSError,struct.error):return False

def prepare(iso,output=ROOT,graphics=False):
    iso=Path(iso).resolve();output=Path(output).resolve()
    source=BaselineInput(iso);read=source.read;entries=source.entries
    engine=read('CCENG.EXE')
    if hashlib.sha256(engine).hexdigest()!=ENGINE_SHA:
        raise ValueError('This bootstrap requires the verified user ISO engine; other versions are resource inputs only')
    gin=gin_stream.parse(source.plain(read('RICHDIMD.GIN')))
    byt=byt_stream.parse(source.plain(read('RICHDIMD.BYT')))
    if not gin['complete'] or not byt['complete']:raise ValueError('Incomplete baseline stream')
    generated=[]
    def write(name,value):
        payload=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        save(output/name,payload);generated.append(name)
    write('evidence/gin-complete-index.json',gin)
    write('evidence/byt-complete-index.json',byt)
    total_levels=0
    for source,target,prefix,count in [('RICHDIMD.LVS','levels','level',80),('DEMO.LVS','demo-levels','demo',5)]:
        if source not in entries:
            write('web/assets/'+target+'.json',dict(source=None,levels=[]));continue
        raw=BaselineInput.plain(read(source));parsed=rdtool.parse_lvs(raw)
        if parsed['count']!=count:raise ValueError('Unexpected baseline level count')
        levels=[dict(id=f"{prefix}-{l['index']}",number=l['index'],name=l['name'],
            rows=rdtool.decode_packed_map(l['_packed']),trailer=l['trailer_hex']) for l in parsed['levels']]
        if prefix=='level':
            for level in levels:level['series']='正式关卡'
        total_levels+=len(levels)
        write('web/assets/'+target+'.json',dict(source=source,sha256=hashlib.sha256(raw).hexdigest(),levels=levels))
    pe=struct.unpack_from('<I',engine,0x3c)[0]
    if engine[pe:pe+4]!=b'PE\0\0':raise ValueError('Invalid PE header')
    n=struct.unpack_from('<H',engine,pe+6)[0];size=struct.unpack_from('<H',engine,pe+20)[0]
    base=struct.unpack_from('<I',engine,pe+24+28)[0];sections=pe+24+size
    tables=[]
    addresses=[0x4511D8,0x451198,0x4511B8,0x4511F8]
    for address in addresses:
        rva=address-base
        for i in range(n):
            vsize,va,rawsize,ptr=struct.unpack_from('<IIII',engine,sections+40*i+8)
            if va<=rva and rva+32<=va+rawsize:
                tables.append(list(struct.unpack_from('<16H',engine,ptr+rva-va)));break
        else:raise ValueError('Coordinate table outside PE section')
    write('evidence/native-coordinate-index-tables.json',dict(exe_sha256=ENGINE_SHA,addresses=[f'{a:X}' for a in addresses],tables=tables))
    # Original WAV effects can be played directly; MIDI/video conversion remains optional.
    effects=[];files=[]
    for record in gin['records']:
        if record['opcode']!=9:continue
        name=record['text'].upper()
        if name not in entries or not name.endswith('.WAV'):continue
        raw=read(name);file=Path(name).name.lower()
        save(output/'web/assets/audio'/file,raw)
        files.append(dict(file=file,source=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        v=record['values_raw'];effects.append(dict(id=v[0],parameter=v[1],limit=v[2],weight=v[3],file=file))
    write('web/assets/audio.json',dict(files=files,effects=effects,music=[],codec='Original WAV; optional MIDI/video conversion not performed'))
    if not (output/'web/assets/optimal-solutions.json').exists():
        write('web/assets/optimal-solutions.json',dict(scope='No certifications shipped in source checkout; generate and verify locally',solutions=[]))
    if graphics:
        from build_web_sprites import main as build_sprites
        from pcx_decode import decode_pcx
        from PIL import Image,ImageDraw
        build_sprites(output,iso)
        for source,target in [('TITLE.PCX','title.png'),('COREC.PCX','company-logo.png'),('THEMAP.PCX','level-map.png')]:
            if source in entries:
                pixels,palette,_=decode_pcx(BaselineInput.plain(read(source)))
                image=Image.fromarray(palette[pixels].astype('uint8'),'RGB')
            else:
                image=Image.new('RGB',(640,100),(17,24,39))
                ImageDraw.Draw(image).text((25,40),'OpenRD - local game resources',fill=(229,231,235))
            buffer=io.BytesIO();image.save(buffer,format='PNG')
            save(output/'web/assets/ui'/target,buffer.getvalue())
    report=dict(prepared=True,levels=total_levels,iso_read_only=True,input_kind='game-folder' if iso.is_dir() else 'iso',engine_executed=False,graphics=graphics,
        engine_sha256=ENGINE_SHA,generated=generated,optional_media='MIDI and video need separate local conversion')
    write('evidence/local-bootstrap.json',report)
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    inputs=ap.add_mutually_exclusive_group(required=True);inputs.add_argument('--iso',type=Path);inputs.add_argument('--game-dir',type=Path)
    ap.add_argument('--output',type=Path,default=ROOT);ap.add_argument('--graphics',action='store_true')
    args=ap.parse_args();print(json.dumps(prepare(args.iso or args.game_dir,args.output,args.graphics),ensure_ascii=False))
