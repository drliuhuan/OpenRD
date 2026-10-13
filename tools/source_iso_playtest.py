"""Play ISO-baseline Game with a local source resource skin, in isolated memory."""
import argparse
import json
import secrets
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from input_http_server import InputHTTPServer
from source_renderer import load_renderers
from source_playtest import PAGE


def serve(import_dir, host='127.0.0.1', port=8771, dataset=None):
    # Requires the existing stable installation. This import is never replaced
    # with a source BYT or another version's game implementation.
    from web_playtest import Game,LEVELS,BYT,GIN,ROOT
    from source_alignment import aligned_game_class
    root=Path(import_dir).resolve()
    bundle=json.loads((root/'framework/bundle.json').read_text(encoding='utf-8'))
    renderers=load_renderers(root,bundle)
    if dataset is None:
        if len(renderers)!=1:raise ValueError('Select one inline resource dataset with --dataset')
        dataset=next(iter(renderers))
    if dataset not in renderers:raise ValueError('Selected source has no inline resource adapter')
    renderer=renderers[dataset]
    if renderer.theme_errors:raise ValueError(renderer.theme_errors)
    tables=json.loads((ROOT/'evidence/native-coordinate-index-tables.json').read_text(encoding='utf-8'))['tables']
    renderer.bind_iso_graphics(BYT,GIN,tables)
    Game=aligned_game_class(renderer,Game)
    levels={level['id']:level for level in LEVELS};sessions={};session_lock=threading.Lock()
    page=PAGE.replace('OpenRD 来源试玩框架','OpenRD ISO 规则资源试玩').replace(
        '从你提供的游戏或试玩数据运行，不需要另备 ISO。可玩关卡以数据自带内容为准；部分早期版本只支持基础画面。',
        '使用 ISO 基准游戏逻辑与关卡，可切换本地导入的资源主题。此试玩使用独立内存会话。')
    def state(game):return dict(game.state(),mode='Source resource display',level=game.scenario)
    class Handler(BaseHTTPRequestHandler):
        def reply(self,code,value,kind='application/json'):
            body=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode('utf-8')
            self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if self.path=='/':return self.reply(200,page.encode('utf-8'),'text/html; charset=utf-8')
            if self.path=='/i18n.js':return self.reply(200,(ROOT/'web/i18n.js').read_bytes(),'text/javascript; charset=utf-8')
            if self.path=='/api/catalog':
                return self.reply(200,dict(levels=[dict(id=l['id'],name=l['name'],loadable=True,variant=None) for l in LEVELS],
                    media=[],preview={},themes={'default':[dict(id=t['id'],name=t['name']) for t in sorted(renderer.themes.values(),key=lambda t:t['index'])]},
                    resource_errors={'default':[]},default_theme=next(iter(sorted(renderer.themes,key=lambda key:renderer.themes[key]['index'])),''),logical_source='User ISO baseline'))
            self.reply(404,dict(error='Not found'))
        def do_POST(self):
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4096:raise ValueError('Invalid request size')
                data=json.loads(self.rfile.read(size))
                if self.path=='/api/start':
                    level=str(data['level']);theme=data.get('theme','')
                    if level not in levels or theme and theme not in renderer.themes:raise ValueError('Unknown level/theme')
                    game=Game(level);token=secrets.token_urlsafe(24)
                    with session_lock:
                        if len(sessions)>=128:sessions.pop(next(iter(sessions)))
                        sessions[token]=dict(game=game,theme=theme,lock=threading.Lock(),playback=None)
                    return self.reply(200,dict(token=token,state=state(game)))
                with session_lock:session=sessions[data['token']]
                game,theme,lock=session['game'],session['theme'],session['lock']
                with lock:
                    if self.path=='/api/state':return self.reply(200,state(game))
                    if type(data.get('revision')) is not int or data['revision']!=game.revision:raise ValueError('Stale state revision')
                    if self.path=='/api/click':
                        if any(type(data[k]) is not int for k in ('x','y')):raise ValueError('Integer coordinates required')
                        initial=game.state()['cells']
                        result=game.click(data['x'],data['y'],data['revision'])
                        run=secrets.token_urlsafe(12)
                        frames=renderer.alignment.expand_backgrounds(result['playback'],initial)
                        session['playback']=dict(id=run,frames=frames,revision=game.revision)
                        return self.reply(200,dict(state(game),playback=dict(id=run,count=len(frames),iso_frames=len(result['playback']),frame_ms=result['frame_ms'])))
                    if self.path=='/api/frame':
                        if type(data.get('time',0)) is not int:raise ValueError('Integer render time required')
                        snapshot=game.state()
                        if 'playback' in data:
                            playback=session['playback'];index=data.get('index')
                            if not playback or data['playback']!=playback['id'] or type(index) is not int or not 0<=index<len(playback['frames']):
                                raise ValueError('Stale or invalid animation frame')
                            snapshot=playback['frames'][index]
                        frame=renderer.render_iso_state(snapshot,data.get('time',0),theme,view_size=data.get('view_size'),camera=data.get('camera'))
                        frame['snapshot']=dict(turn=snapshot['turn'],diamonds=snapshot['diamonds'],player=snapshot['player'],transition=snapshot['transition'])
                        return self.reply(200,frame)
                self.reply(404,dict(error='Not found'))
            except (ValueError,KeyError,TypeError) as exc:self.reply(400,dict(error=str(exc)))
        def log_message(self,*args):pass
    server=InputHTTPServer((host,port),Handler)
    print(f'OpenRD imported model: http://{host}:{server.server_port}',flush=True)
    server.serve_forever()


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('import_dir',type=Path)
    ap.add_argument('--host',default='127.0.0.1');ap.add_argument('--port',type=int,default=8771);ap.add_argument('--dataset')
    args=ap.parse_args();serve(args.import_dir,args.host,args.port,args.dataset)
