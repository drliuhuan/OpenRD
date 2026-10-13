"""Select local game inputs by format priority without executing programs."""
import os
from pathlib import Path
import struct

EXCLUDED={'crack','cracks','keygen','patches','.git','__pycache__','imports','local-tools'}

def file_header(path):
    """Reject obvious unsupported/truncated headers using bounded reads."""
    suffix=path.suffix.lower();size=path.stat().st_size
    with path.open('rb') as stream:
        head=stream.read(64)
        if suffix=='.iso':
            if size<17*2048:raise ValueError('ISO header is truncated')
            stream.seek(16*2048)
            if stream.read(7)!=b'\x01CD001\x01':raise ValueError('Not a supported ISO9660 header')
        elif suffix=='.cab':
            if head[:4]==b'MSCF':
                if len(head)<36 or not 36<=struct.unpack_from('<I',head,8)[0]<=size:
                    raise ValueError('Invalid Microsoft CAB header')
            elif head[:4]==b'ISc(':
                if size<20:raise ValueError('InstallShield CAB header is truncated')
            else:raise ValueError('Unsupported CAB header')
        elif suffix=='.exe':
            if len(head)<64 or head[:2]!=b'MZ':raise ValueError('Invalid executable header')
            offset=struct.unpack_from('<I',head,60)[0]
            if not 64<=offset<=min(size-24,2*1024*1024):raise ValueError('Invalid PE header offset')
            stream.seek(offset);pe=stream.read(24)
            if pe[:4]!=b'PE\0\0':raise ValueError('Unsupported executable header')
            optional=struct.unpack_from('<H',pe,20)[0]
            if optional<2 or offset+24+optional>size:raise ValueError('Truncated PE optional header')
            if stream.read(2) not in (b'\x0b\x01',b'\x0b\x02'):raise ValueError('Unsupported PE optional header')
        else:
            # Explicit legacy archive/disc paths remain handled by the importer.
            if not head:raise ValueError('Empty input file')
    return True


def game_directory(path):
    if (path/'framework/bundle.json').is_file():return True
    files={p.name.casefold():p for p in path.iterdir() if p.is_file() and not p.is_symlink()}
    byts=[p for p in files.values() if p.suffix.lower()=='.byt']
    if not byts:return False
    if not any(p.suffix.lower()=='.gin' for p in files.values()) and 'cceng.exe' not in files:return False
    for p in byts:
        with p.open('rb') as stream:head=stream.read(8)
        if head[:1]==b'\xca' or head[:2]==b'\xcb\xfe' or head.startswith(b'CCIb'):return True
    return False


def discover(source):
    source=Path(source).resolve()
    if not source.exists():raise ValueError('Input does not exist / 输入不存在: '+str(source))
    skipped=[]
    if source.is_file():
        file_header(source)
        return [source],skipped
    groups={0:[],1:[],2:[],3:[]};count=0
    for current,dirs,names in os.walk(source,followlinks=False):
        folder=Path(current)
        depth=len(folder.relative_to(source).parts)
        dirs[:]=sorted(d for d in dirs if d.casefold() not in EXCLUDED and not (folder/d).is_symlink()) if depth<4 else []
        count+=len(dirs)+len(names)
        if count>10000:raise ValueError('Input scan exceeds 10000 entries')
        try:
            if game_directory(folder):groups[1].append(folder)
        except (OSError,ValueError) as exc:skipped.append(dict(path=str(folder),reason=str(exc)))
        for name in sorted(names,key=str.casefold):
            p=folder/name;suffix=p.suffix.lower()
            if suffix not in ('.iso','.cab','.exe') or p.is_symlink():continue
            if name.casefold() in ('cceng.exe','ccnteng.exe','rich diamond.exe','rdconfig.exe'):continue
            if any(word in p.stem.casefold() for word in ('crack','keygen','patch')):continue
            try:file_header(p)
            except (OSError,ValueError) as exc:
                skipped.append(dict(path=str(p),reason=str(exc)));continue
            groups[{'.iso':0,'.cab':2,'.exe':3}[suffix]].append(p)
    choices=[]
    for priority in range(4):
        choices.extend(sorted(groups[priority],key=lambda p:(len(p.relative_to(source).parts),str(p.relative_to(source)).casefold())))
    if not choices:raise ValueError('No supported input found / 未找到可解析的 ISO、游戏目录、CAB 或 EXE: '+str(source))
    return choices,skipped
