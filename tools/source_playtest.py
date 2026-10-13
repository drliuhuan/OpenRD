"""Play user data without an ISO through the shared ISO-derived CPU interpreter."""
import argparse
import json
import secrets
import threading
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler
from input_http_server import InputHTTPServer
from byt_world import World
from byt_input_queue import Command
from byt_target_commands import commands


class ModelGame:
    def __init__(self, level, byt, renderer=None, theme=''):
        self.level = level
        self.renderer = renderer
        self.theme = theme
        self.object_ids = {r['byte_raw']:r['words_raw'][3]&255 for r in byt['records'] if r['opcode']==2}
        self.world = World(level['rows'], byt)
        if renderer:
            self.world.graphic_map_size=renderer.map_size
            self.world.graphic_masks=bytearray(renderer.map_size[0]*renderer.map_size[1])
            definitions={}
            for r in byt['records']:
                if r['opcode']==1:definitions.setdefault(r['tile_code'],r)
            for y,row in enumerate(level['rows']):
                for x,tile in enumerate(row):
                    self.world.graphic_masks[y*renderer.map_size[0]+x]=definitions[tile]['last_byte_raw']
        self.world.initialize_new_display_slots()
        self.world.apply_collection_setting_slice(0)
        self.world.enable_map_rules(level['rows'])
        self.world.schedule_map_load_objects()
        result = self.world.advance_input_cycle()
        self.diagnostic = result.get('diagnostic') if not result['complete'] else None
        self.turn = 0
        self.revision = 1
        self.lock = threading.Lock()
        self.by_class = {}
        for record in byt['records']:
            if record['opcode'] == 1:
                self.by_class.setdefault((record['leading_bytes_raw'][1], record['parameter_raw']), record['tile_code'])

    def state(self):
        w = self.world
        cells = [[dict(tile=self.by_class.get((w.classes[y*128+x], w.parameters[y*128+x]), tile),
                       cls=w.classes[y*128+x], parameter=w.parameters[y*128+x],
                       mask=w.graphic_masks[y*w.graphic_map_size[0]+x] if w.graphic_masks is not None else 0,
                       resource=w.resources.get((x,y),0)) for x,tile in enumerate(row)]
                 for y,row in enumerate(self.level['rows'])]
        while len(cells)>1 and all(c['tile']==32 for c in cells[-1]):cells.pop()
        return dict(level=self.level['id'], dataset=self.level.get('dataset'), cells=cells, player=list(w.player.position) if w.player and not w.player.disposed else None,
                    actors=[dict(x=vm.position[0],y=vm.position[1],program=p,object=self.object_ids.get(p,0),
                                 action=next((m['action'] for m in reversed(w.moves) if tuple(m['new'])==vm.position
                                              and m['player']==(vm is w.player)),0)) for p,vm in w.instances if not vm.disposed],
                    turn=self.turn, revision=self.revision, diamonds=w.collectible_count,
                    transition=w.pending_transition, diagnostic=self.diagnostic,
                    completed=bool(w.pending_transition and w.pending_transition['kind'] in (3,6)
                                   and w.pending_transition['mode']==0 and w.collectible_count==0),
                    mode='Source resource display' if self.renderer else 'Experimental CPU model; logical display')

    def click(self, x, y, revision):
        if revision != self.revision:
            raise ValueError('Stale state; reload before clicking')
        if not (0<=y<len(self.level['rows']) and 0<=x<len(self.level['rows'][y])):
            raise ValueError('Target outside map')
        w=self.world
        if self.diagnostic or not w.player or w.player.disposed or w.pending_transition:
            return self.state()
        start=w.player.position
        kinds=commands(start,(x,y),0)
        if len(kinds)>128:
            raise ValueError('Target exceeds canvas')
        for kind in kinds:
            w.input_queue.append(0,Command(kind))
            for _ in range(100):
                result=w.advance_input_cycle()
                if not result['complete']:
                    self.diagnostic=result.get('diagnostic');break
                if not w.input_queue.head() and not w.scheduler.queues[2] and not w.scheduler.queues[3]:
                    break
            else:self.diagnostic='Model cycle budget exceeded'
            self.turn+=1;self.revision+=1
            if self.diagnostic or w.pending_transition or not w.player or w.player.disposed:
                break
            axis=0 if start[0]!=x else 1
            direction=1 if (x,y)[axis]>start[axis] else -1
            if start!=(x,y) and (w.player.position[axis]-(x,y)[axis])*direction>=0:
                break
        return self.state()


PAGE = '''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="icon" href="data:,">
<title>OpenRD - Rich Diamond 开源重实现引擎</title><style>body{margin:20px;background:#111827;color:#e5e7eb;font:16px system-ui}button,select{font:inherit;padding:7px;margin:4px}canvas{background:#252f43;image-rendering:pixelated;max-width:100%;touch-action:manipulation}#wrap{overflow:auto}#notice{color:#fbbf24}a{color:#93c5fd}</style>
<script src="/i18n.js"></script><h1>OpenRD</h1><p>OpenRD 来源试玩框架</p><p id="notice">从你提供的游戏或试玩数据运行，不需要另备 ISO。可玩关卡以数据自带内容为准；部分早期版本只支持基础画面。</p>
<select id="levels" aria-label="关卡"></select><select id="themes" aria-label="资源主题"></select><button id="reset">重新开始</button><label><input id="full-map" type="checkbox">全图</label><p id="status"></p><div id="wrap"><canvas id="map"></canvas></div><details><summary>已接入的本地媒体</summary><div id="media"></div></details>
<script>
'use strict';let state,token,busy=false,preview={},previews={},frame=null,paintId=0,themeCatalog={},levelDatasets={},idleController=null,camera=null;const images={};const canvas=document.getElementById('map'),ctx=canvas.getContext('2d');const cell=24;
const api=async(path,data,signal)=>{const r=await fetch(path,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal}:{signal});const v=await r.json();if(!r.ok)throw Error(v.error);return v;};
function visualTime(){return Math.floor(performance.now()*25/1000);}
function outcome(s){return s.diagnostic||(s.completed?'已通关，可选择其他关卡':!s.player?'本轮结束，点击重新开始':s.transition?'本轮结束，点击重新开始':'点击人物同行或同列移动');}
function viewport(){if(document.getElementById('full-map').checked)return null;const dpr=Math.min(2,devicePixelRatio||1);return [Math.max(320,Math.min(1200,Math.round((innerWidth-40)*dpr))),Math.max(320,Math.min(1000,Math.round(innerHeight*.72*dpr)))];}
async function draw(s,extra={}){state=s;const id=++paintId,expectedToken=token;
if(s.mode==='Source resource display'){const f=await api('/api/frame',{token,revision:s.revision,time:visualTime(),view_size:viewport(),camera,...extra},extra.idle?idleController?.signal:undefined);if(id!==paintId||expectedToken!==token||(extra.idle&&busy))return;const image=new Image();await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('资源图像加载失败'));image.src=f.image;});if(id!==paintId||expectedToken!==token||(extra.idle&&busy))return;frame=f;camera=f.camera||null;if(canvas.width!==f.width)canvas.width=f.width;if(canvas.height!==f.height)canvas.height=f.height;ctx.imageSmoothingEnabled=false;ctx.drawImage(image,0,0);document.getElementById('status').textContent=`步数 ${f.snapshot?.turn??s.turn} · 钻石 ${f.snapshot?.diamonds??s.diamonds} · ${outcome(s)}`+(f.missing.length?` · ${f.missing.length} 个资源未绘制`:'');return;}
frame=null;camera=null;
const selectedPreview=previews[s.dataset]||preview;const width=Math.max(...s.cells.map(r=>r.length));canvas.width=width*cell;canvas.height=s.cells.length*cell;
s.cells.forEach((row,y)=>row.forEach((c,x)=>{ctx.fillStyle=c.cls===0?'#111827':c.cls===1?'#64748b':c.cls===2?'#344453':'#574c41';ctx.fillRect(x*cell,y*cell,cell-1,cell-1);let drawn=false;(selectedPreview[c.resource]||[]).forEach(p=>{const image=images[p.path];if(image){ctx.drawImage(image,...p.crop,x*cell+p.offset[0]/2,y*cell+p.offset[1]/2,p.crop[2]/2,p.crop[3]/2);drawn=true;}});if(c.cls>2&&!drawn){ctx.fillStyle='#d1d5db';ctx.font='11px monospace';ctx.fillText(c.tile.toString(16).toUpperCase(),x*cell+4,y*cell+16);}}));
s.actors.forEach(a=>{ctx.fillStyle=a.program===1?'#fde047':'#f87171';ctx.beginPath();ctx.arc(a.x*cell+12,a.y*cell+12,8,0,7);ctx.fill();ctx.fillStyle='#111827';ctx.font='11px monospace';ctx.fillText(a.program,a.x*cell+8,a.y*cell+16);});
document.getElementById('status').textContent=`步数 ${s.turn} · 钻石 ${s.diamonds} · ${outcome(s)}`;}
function setBusy(value){busy=value;if(value)idleController?.abort();document.getElementById('full-map').disabled=value;document.getElementById('levels').disabled=value;document.getElementById('themes').disabled=value;document.getElementById('reset').disabled=value;}
function updateThemes(){const select=document.getElementById('themes'),old=select.value;select.replaceChildren();for(const t of [{id:'',name:'GIN 默认素材'},...(themeCatalog[levelDatasets[document.getElementById('levels').value]||'default']||[])]){const o=document.createElement('option');o.value=t.id;o.textContent=t.name;select.append(o);}if([...select.options].some(o=>o.value===old))select.value=old;select.hidden=select.options.length===1;}
async function start(){if(busy)return;setBusy(true);state=null;camera=null;try{const r=await api('/api/start',{level:document.getElementById('levels').value,theme:document.getElementById('themes').value});token=r.token;await draw(r.state);}catch(e){document.getElementById('status').textContent=e.message;}finally{setBusy(false);}}
document.getElementById('full-map').onchange=()=>{camera=null;if(state&&!busy)draw(state);};document.getElementById('reset').onclick=start;document.getElementById('levels').onchange=()=>{updateThemes();start();};document.getElementById('themes').onchange=start;
canvas.onclick=async e=>{if(busy||!state)return;setBusy(true);try{const b=canvas.getBoundingClientRect();let px=(e.clientX-b.left)*canvas.width/b.width,py=(e.clientY-b.top)*canvas.height/b.height,x,y;if(frame){px-=frame.origin[0]+(frame.hit_offset?.[0]||0);py-=frame.origin[1]+(frame.hit_offset?.[1]||0);const [a,b,c,d]=frame.basis,det=a*d-b*c;x=Math.round((d*px-c*py)/det);y=Math.round((a*py-b*px)/det);}else{x=Math.floor(px/cell);y=Math.floor(py/cell);}const result=await api('/api/click',{token,revision:state.revision,x,y});if(result.playback?.count){state=result;await playResourceFrames(result,result.playback);}await draw(result);}catch(e){document.getElementById('status').textContent=e.message;}finally{setBusy(false);}};
async function playResourceFrames(s,run){const start=performance.now();let shown=-1;while(shown<run.count-1){const index=Math.min(run.count-1,Math.floor((performance.now()-start)/run.frame_ms));if(index===shown){await new Promise(resolve=>setTimeout(resolve,Math.max(1,run.frame_ms-(performance.now()-start)%run.frame_ms)));continue;}await draw(s,{playback:run.id,index});shown=index;}}
let ambientPending=false,lastAmbient=0;async function ambient(){const now=performance.now(),interval=frame&&frame.width*frame.height>4000000?200:40;if(!busy&&!ambientPending&&state?.mode==='Source resource display'&&!document.hidden&&!matchMedia('(prefers-reduced-motion: reduce)').matches&&now-lastAmbient>=interval){ambientPending=true;lastAmbient=now;idleController=new AbortController();try{await draw(state,{idle:true});}catch(e){if(e.name!=='AbortError'&&!e.message.includes('Stale'))document.getElementById('status').textContent=e.message;}finally{ambientPending=false;}}requestAnimationFrame(ambient);}requestAnimationFrame(ambient);
api('/api/catalog').then(async c=>{preview=c.preview||{};previews=c.previews||{};themeCatalog=c.themes||{};c.levels.forEach(l=>levelDatasets[l.id]=l.dataset);const components=[...Object.values(preview).flat(),...Object.values(previews).flatMap(p=>Object.values(p).flat())];await Promise.all([...new Set(components.map(p=>p.path))].map(path=>new Promise(resolve=>{const i=new Image();i.onload=()=>{images[path]=i;resolve();};i.onerror=resolve;i.src='/media/'+encodeURIComponent(path);})));const select=document.getElementById('levels');c.levels.forEach(l=>{const o=document.createElement('option');o.value=l.id;o.textContent=l.name+(l.variant===null?'':` · 映射表 ${l.variant}`);o.disabled=!l.loadable;select.append(o);});c.media.forEach(m=>{const p=document.createElement('p'),a=document.createElement('a');a.textContent=m.source;a.href='/media/'+encodeURIComponent(m.path);a.target='_blank';a.rel='noopener';p.append(a);document.getElementById('media').append(p);});updateThemes();if(c.default_theme)document.getElementById('themes').value=c.default_theme;start();}).catch(e=>document.getElementById('status').textContent=e.message);
</script>'''


def serve(import_dir,host='127.0.0.1',port=8770):
    root=Path(import_dir).resolve()
    bundle=json.loads((root/'framework/bundle.json').read_text(encoding='utf-8'))
    from source_access import require_playable
    require_playable(bundle)
    scripts={path:json.loads((root/path).read_text(encoding='utf-8'))
             for path in {l.get('byt',bundle['byt']) for l in bundle['levels']}}
    levels={l['id']:l for l in bundle['levels']}
    from source_renderer import load_renderers
    renderers=load_renderers(root,bundle)
    sessions={};session_lock=threading.Lock()
    media={m['path'] for m in bundle['media']}
    class Handler(BaseHTTPRequestHandler):
        def reply(self,status,data,kind='application/json'):
            body=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
        def do_GET(self):
            from urllib.parse import unquote
            path=urlparse(self.path).path
            if path=='/':return self.reply(200,PAGE.encode(),'text/html; charset=utf-8')
            if path=='/i18n.js':return self.reply(200,(Path(__file__).resolve().parent.parent/'web/i18n.js').read_bytes(),'text/javascript; charset=utf-8')
            if path=='/api/catalog':
                catalog=dict({k:bundle[k] for k in ('levels','profiles','media','limitations','preview','previews','datasets') if k in bundle},
                    themes={key or 'default': [dict(id=t['id'],name=t['name']) for t in sorted(r.themes.values(),key=lambda t:t['index'])] for key,r in renderers.items()},
                    resource_errors={key or 'default':r.theme_errors for key,r in renderers.items()},requires_iso=False)
                if None in renderers and renderers[None].themes:
                    catalog['default_theme']=min(renderers[None].themes,key=lambda key:renderers[None].themes[key]['index'])
                return self.reply(200,catalog)
            if path.startswith('/media/'):
                name=unquote(path[7:]);p=(root/name).resolve()
                if name in media and root in p.parents and p.is_file():
                    import mimetypes
                    return self.reply(200,p.read_bytes(),mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
            self.reply(404,dict(error='Not found'))
        def do_POST(self):
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4096:raise ValueError('Invalid request size')
                data=json.loads(self.rfile.read(size))
                if self.path=='/api/start':
                    level=levels[str(data['level'])]
                    if not level['loadable']:raise ValueError('Unsupported tiles')
                    renderer=renderers.get(level.get('dataset'));theme=data.get('theme','')
                    if theme and (not renderer or theme not in renderer.themes):raise ValueError('Unknown source theme')
                    game=ModelGame(level,scripts[level.get('byt',bundle['byt'])],renderer,theme);token=secrets.token_urlsafe(24)
                    with session_lock:
                        if len(sessions)>=128:sessions.pop(next(iter(sessions)))
                        sessions[token]=game
                    return self.reply(200,dict(token=token,state=game.state()))
                if self.path=='/api/click':
                    with session_lock:game=sessions[data['token']]
                    if any(type(data[k]) is not int for k in ('x','y','revision')):raise ValueError('Integer coordinates required')
                    with game.lock:state=game.click(data['x'],data['y'],data['revision'])
                    return self.reply(200,state)
                if self.path=='/api/state':
                    with session_lock:game=sessions[data['token']]
                    with game.lock:state=game.state()
                    return self.reply(200,state)
                if self.path=='/api/frame':
                    with session_lock:game=sessions[data['token']]
                    if type(data.get('revision')) is not int or type(data.get('time',0)) is not int:
                        raise ValueError('Integer render inputs required')
                    with game.lock:
                        if data['revision']!=game.revision:raise ValueError('Stale render revision')
                        if not game.renderer:raise ValueError('No inline resource renderer for this source')
                        frame=game.renderer.render(game.state(),data.get('time',0),theme=game.theme,
                            view_size=data.get('view_size'),camera=data.get('camera'))
                    return self.reply(200,frame)
                self.reply(404,dict(error='Not found'))
            except (ValueError,KeyError,TypeError) as exc:self.reply(400,dict(error=str(exc)))
        def log_message(self,*args):pass
    server=InputHTTPServer((host,port),Handler)
    print(f'OpenRD imported model: http://{host}:{server.server_port}',flush=True)
    server.serve_forever()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('import_dir',type=Path);parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8770)
    args=parser.parse_args()
    try:serve(args.import_dir,args.host,args.port)
    except ValueError as exc:parser.exit(2,str(exc)+'\n')
