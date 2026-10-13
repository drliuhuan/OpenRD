"""Resolve InstallShield extraction tools only when the format requires them."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parent.parent
PACKAGES={
    'x64':('unshield-1.6.2-x64.7z','662fefefc6988a3744ddc6b5b8d2e96ac21876d532f7d23a597c4ca797764a6b'),
    'x86':('unshield-1.6.2-x86.7z','96eebfae4c6f81c67fb9dbd5b2108c8ab633cc140956354670b5298335cadad9'),
    'arm64':('unshield-1.6.2-arm64.7z','3adddf7ab87e302389918da07c42332f2bcd7afa13d5c9ddc8345b035f3dbce0'),
}
DOWNLOAD_PAGE='https://github.com/ScoopInstaller/Main/blob/master/bucket/unshield.json'

def download_archive(url):
    try:
        with urlopen(Request(url,headers={'User-Agent':'OpenRD runtime tool installer'}),timeout=20) as response:
            chunks=[];size=0
            while True:
                chunk=response.read(65536)
                if not chunk:break
                size+=len(chunk)
                if size>32*1024*1024:raise RuntimeError('Tool download exceeds 32 MiB')
                chunks.append(chunk)
        return b''.join(chunks)
    except OSError:
        curl=shutil.which('curl.exe') if os.name=='nt' else None
        if not curl:raise
        print('使用 Windows curl 通过 HTTPS 重试 / Retrying HTTPS with Windows curl.',flush=True)
        with tempfile.TemporaryDirectory(prefix='openrd-tool-download-') as temp:
            target=Path(temp)/'download.7z'
            result=subprocess.run([curl,'--fail','--silent','--show-error','--location','--proto','=https',
                                   '--connect-timeout','10','--max-time','35','--max-filesize','33554432',url,'--output',str(target)],
                                  capture_output=True,timeout=40,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode:raise OSError('HTTPS download failed: '+result.stderr.decode(errors='replace')[-300:])
            if target.stat().st_size>32*1024*1024:raise RuntimeError('Tool download exceeds 32 MiB')
            return target.read_bytes()

def find_unshield(explicit=None):
    if explicit:
        found=str(Path(explicit).resolve()) if Path(explicit).is_file() else shutil.which(str(explicit))
        if found:return found
        raise RuntimeError('unshield path does not exist / unshield路径不存在: '+str(explicit))
    candidates=[os.environ.get('OPENRD_UNSHIELD'),shutil.which('unshield'),
                ROOT/'local-tools/unshield/unshield.exe',ROOT/'tools/unshield.exe']
    candidates.extend(sorted((ROOT/'local-tools').glob('unshield-scoop-*/unshield.exe')))
    for item in candidates:
        if item and Path(item).is_file():return str(Path(item).resolve())
    return None

def resolve_unshield(explicit=None,seven='7z',download=False):
    existing=find_unshield(explicit)
    if existing:return existing
    message='InstallShield需要unshield / unshield is required for InstallShield. Download: '+DOWNLOAD_PAGE
    print(message,flush=True)
    if not download:raise RuntimeError(message+'; enable automatic tools download or use --unshield')
    if os.name!='nt':raise RuntimeError(message+'; install unshield using your OS package manager (e.g. apt install unshield)')
    arch='arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x64' if sys.maxsize>2**32 else 'x86'
    filename,expected=PACKAGES[arch]
    url='https://raw.githubusercontent.com/ScoopInstaller/Binary/master/unshield/'+filename
    print('自动下载并校验 / Downloading and verifying: '+url,flush=True)
    try:
        raw=download_archive(url)
        if hashlib.sha256(raw).hexdigest()!=expected:raise RuntimeError('unshield download checksum mismatch')
        from import_source import unpack,save
        with tempfile.TemporaryDirectory(prefix='openrd-unshield-') as temp:
            work=Path(temp);archive=work/filename;archive.write_bytes(raw)
            extracted=work/'files';logs=[]
            unpack(archive,extracted,seven,None,logs,process_cabs=False)
            binaries=list(extracted.rglob('unshield.exe'))
            if len(binaries)!=1:raise RuntimeError('Downloaded archive has no unique unshield.exe')
            folder=binaries[0].parent
            destination=ROOT/'local-tools'/('unshield-scoop-1.6.2-'+arch)
            for p in folder.rglob('*'):
                if p.is_file():save(destination/p.relative_to(folder),p.read_bytes())
            save(destination/'download.json',(json.dumps(dict(url=url,sha256=expected,version='1.6.2',provider='ScoopInstaller'))+'\n').encode())
        return str(destination/'unshield.exe')
    except (OSError,ValueError) as exc:
        raise RuntimeError(message+'; automatic download failed / 自动下载失败: '+str(exc)) from exc
