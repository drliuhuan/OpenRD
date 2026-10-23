"""One public launcher for ISO, installed folders and demo resource inputs."""
import argparse
import errno
import hashlib
import json
import socket
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from import_source import inspect as import_input,save
from prepare_iso import can_prepare,prepare as prepare_baseline,BaselineInput

ROOT=Path(__file__).resolve().parent.parent

def _prepare_selected(source,cache=None,mode='auto',seven='7z',unshield=None,engine=None,auto_tools=True):
    source=Path(source).resolve()
    if not source.exists():raise ValueError('Input does not exist: '+str(source))
    cache=Path(cache or ROOT/'imports/runs').resolve()
    if source.is_dir() and (source==cache or source in cache.parents):
        raise ValueError('The run directory must be outside the input folder')
    if mode not in ('auto','baseline','source','animation'):raise ValueError('Unknown preparation mode')
    baseline=can_prepare(source) if mode not in ('source','animation') else False
    if mode=='baseline' and not baseline:raise ValueError('Input is not the verified ISO baseline or matching game folder')
    cache.mkdir(parents=True,exist_ok=True)
    run=Path(tempfile.mkdtemp(prefix='run-',dir=cache))
    if baseline:
        app=run/'app'
        for folder,suffixes in (('tools',{'.py','.cjs','.json'}),('web',{'.html','.js','.css'})):
            for p in (ROOT/folder).iterdir():
                if p.is_file() and p.suffix in suffixes:save(app/folder/p.name,p.read_bytes())
        try:result=prepare_baseline(source,app,True)
        except ImportError as exc:
            raise ValueError('ISO graphics build requires Pillow and NumPy: python -m pip install -r requirements-build.txt') from exc
        reader=BaselineInput(source)
        identity=hashlib.sha256(b''.join(hashlib.sha256(reader.read(n)).digest() for n in
            ('CCENG.EXE','RICHDIMD.GIN','RICHDIMD.BYT','RICHDIMD.LVS','DEMO.LVS') if n in reader.entries)).hexdigest()[:20]
        report=dict(mode='baseline',input=str(source),input_kind=result['input_kind'],levels=result['levels'],
            run=str(run),app=str(app),data=str(cache/'data'/identity),requires_iso=False if source.is_dir() else True,
            native_program_executed=False,ready=True,logic='Verified ISO baseline Game')
    else:
        if source.is_dir() and (source/'framework/bundle.json').is_file():
            imported=source;result=None
        else:
            imported=run/'resources'
            catalog=ROOT/'known-artifacts.json'
            result=import_input(source,imported,seven,unshield,catalog if catalog.exists() else None,engine,auto_tools=auto_tools)
        bundle=json.loads((imported/'framework/bundle.json').read_text(encoding='utf-8'))
        from source_access import require_playable
        if mode!='animation':require_playable(bundle)
        if mode=='animation' and not (bundle.get('gin') or bundle.get('datasets')):
            raise ValueError('No source graphics in this old import; reimport the original installer / 旧导入缺少图形，请重新导入原安装包')
        loadable=sum(bool(level.get('loadable')) for level in bundle['levels'])
        if not loadable and mode!='animation':raise ValueError('Input has no supported playable levels')
        report=dict(mode='animation' if mode=='animation' else 'source',input=str(source),input_kind='imported-data' if result is None else result['source_kind'],
            levels=len(bundle['levels']),loadable=loadable,run=str(run),resources=str(imported),
            requires_iso=False,native_program_executed=False,ready=True,
            logic='Same ISO-derived CPU interpreter; source declarations are input data, not native-version equivalence')
    save(run/'run.json',json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8'))
    return report

def prepare(source=None,cache=None,mode='auto',seven='7z',unshield=None,engine=None,auto_tools=True):
    from play_inputs import discover
    from source_access import MESSAGE
    original=Path(source or ROOT/'game').resolve()
    choices,skipped=discover(original)
    failures=[]
    for selected in choices:
        try:report=_prepare_selected(selected,cache,mode,seven,unshield,engine,auto_tools)
        except ValueError as exc:
            # Access denial is not a parsing error and must never cause fallback.
            if str(exc)==MESSAGE or 'requires Pillow' in str(exc):raise
            failures.append(dict(path=str(selected),reason=str(exc)));continue
        report['selection']=dict(requested=str(original),selected=str(selected),priority='ISO > game directory > CAB > EXE',
                                 skipped_headers=skipped,parse_failures=failures)
        save(Path(report['run'])/'run.json',json.dumps(report,ensure_ascii=False,indent=2).encode())
        return report
    raise ValueError('No playable parsed input / 无可用输入: '+ '; '.join(f['path']+': '+f['reason'] for f in failures))

def stop_child(child):
    """Reap the owned service even if Ctrl+C is pressed again during shutdown."""
    previous=signal.signal(signal.SIGINT,signal.SIG_IGN)
    try:
        if child.poll() is None:
            child.terminate()
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=3)
    finally:
        signal.signal(signal.SIGINT,previous)


def wait_for_exit(child):
    # A blocking Windows WaitForSingleObject(INFINITE) defers Python SIGINT.
    # Short, interruptible sleeps let the main thread process console Ctrl+C.
    while child.poll() is None:
        time.sleep(.1)


def choose_port(host,start=8770):
    for candidate in range(start,65536):
        with socket.socket() as probe:
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            try:probe.bind((host,candidate))
            except OSError as exc:
                if exc.errno in (errno.EADDRINUSE,errno.EACCES) or getattr(exc,'winerror',None) in (10048,10013):continue
                raise
            return candidate
    raise RuntimeError('No available port from '+str(start)+' / 无可用端口')


def launch(report,host='127.0.0.1',port=None,trusted=None):
    if port is None:port=choose_port(host)
    if not 0<=port<=65535:raise ValueError('Invalid port')
    from input_http_server import trusted_hosts
    trusted_hosts(host,trusted)
    with socket.socket() as reservation:
        if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
            reservation.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        try:
            reservation.bind((host,port));port=reservation.getsockname()[1]
        except OSError as exc:raise RuntimeError('Server port is unavailable: '+str(port)) from exc
    if report['mode']=='baseline':
        command=[sys.executable,'-B',str(Path(report['app'])/'tools/baseline_server.py'),
            '--host',host,'--port',str(port),'--data-dir',report['data']]
        ready='/api/levels'
    else:
        from source_access import require_playable
        bundle=json.loads((Path(report['resources'])/'framework/bundle.json').read_text(encoding='utf-8'))
        if report['mode']!='animation':require_playable(bundle)
        command=[sys.executable,'-S','-B',str(ROOT/'tools/source_playtest.py'),report['resources'],
            '--host',host,'--port',str(port)]
        ready='/api/catalog'
    if trusted is not None:command.extend(['--trusted-hosts',trusted])
    log=Path(report['run'])/'server.log'
    with log.open('wb') as stream:
        child=subprocess.Popen(command,stdout=stream,stderr=stream,stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    url='http://'+('127.0.0.1' if host=='0.0.0.0' else host)+':'+str(port)
    try:
        for _ in range(100):
            if child.poll() is not None:raise RuntimeError(log.read_text(encoding='utf-8',errors='replace'))
            if f'http://{host}:{port}' not in log.read_text(encoding='utf-8',errors='replace'):
                time.sleep(.1);continue
            try:
                with urlopen(url+ready,timeout=1) as response:
                    if response.status==200:break
            except (URLError,OSError):pass
            time.sleep(.1)
        else:raise RuntimeError('Server startup timed out; log: '+str(log))
    except BaseException:
        stop_child(child);raise
    report=dict(report,url=url,pid=child.pid,log=str(log))
    save(Path(report['run'])/'run.json',json.dumps(report,ensure_ascii=False,indent=2).encode())
    return child,report

def open_browser(url):
    import webbrowser
    try:
        if webbrowser.open(url,new=2):return True
    except (OSError,webbrowser.Error):pass
    print('请手动打开 / Open manually: '+url,flush=True)
    return False

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('source',type=Path,nargs='?',help='File/folder; defaults to project game folder')
    ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,help='Fixed port; omitted: first free port starting at 8770')
    ap.add_argument('--cache',type=Path);ap.add_argument('--mode',choices=['auto','baseline','source','animation'],default='auto')
    ap.add_argument('--seven-zip',default='7z');ap.add_argument('--unshield');ap.add_argument('--engine',type=Path)
    ap.add_argument('--prepare-only',action='store_true')
    ap.add_argument('--no-browser',action='store_true',help='Do not open the default browser')
    ap.add_argument('--trusted-hosts','--trustedhosts',help='Comma-separated exact Host names/IPs; loopback is always allowed')
    ap.add_argument('--no-download-tools',action='store_true',help='Do not automatically download a missing InstallShield tool')
    args=ap.parse_args()
    if args.port is not None and not 0<=args.port<=65535:ap.error('port must be 0..65535')
    try:
        report=prepare(args.source,args.cache,args.mode,args.seven_zip,args.unshield,args.engine,auto_tools=not args.no_download_tools)
        if args.prepare_only:print(json.dumps(report,ensure_ascii=False),flush=True);return
        child,report=launch(report,args.host,args.port,args.trusted_hosts)
        try:
            print('OpenRD: '+report['url'],flush=True)
            print('Input: '+report['input_kind']+'; '+str(report['levels'])+' levels. Run: '+report['run'],flush=True)
            if args.host=='0.0.0.0':print('局域网 / LAN: http://<此电脑IP / this computer IP>:'+str(report['url'].rsplit(':',1)[-1]),flush=True)
            if not args.no_browser:open_browser(report['url'])
            wait_for_exit(child)
        except KeyboardInterrupt:
            print('\nOpenRD 已停止 / Stopped.',flush=True)
        finally:
            stop_child(child)
    except KeyboardInterrupt:
        print('\nOpenRD 已取消 / Cancelled.',flush=True)
    except (ValueError,RuntimeError,KeyError,OSError) as exc:ap.exit(2,str(exc)+'\n')

if __name__=='__main__':main()
