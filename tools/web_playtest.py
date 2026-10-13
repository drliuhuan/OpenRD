"""Game sessions and HTTP API for user-provided Rich Diamond data."""
import json
import gzip
import secrets
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from http.cookies import SimpleCookie,CookieError
from web_storage import Storage
from web_sessions import SessionStore,SessionCapacityError
from byt_world import World
from byt_input_queue import Command
from byt_target_commands import commands
from native_music_selector import MusicSelector
from functools import lru_cache
from byt_map_selector import select_background

ROOT=Path(__file__).resolve().parent.parent
BYT=json.loads((ROOT/'evidence/byt-complete-index.json').read_text(encoding='utf-8'))
GIN=json.loads((ROOT/'evidence/gin-complete-index.json').read_text(encoding='utf-8'))
DEMOS=json.loads((ROOT/'web/assets/demo-levels.json').read_text(encoding='utf-8'))['levels']
DEMO_BY_ID={level['id']:level for level in DEMOS}
FORMAL=json.loads((ROOT/'web/assets/levels.json').read_text(encoding='utf-8'))['levels']
LEVELS=DEMOS+FORMAL
LEVEL_BY_ID={level['id']:level for level in LEVELS}
DEFS={}
for row in BYT['records']:
    if row['opcode']==1 and row['tile_code']:DEFS.setdefault(row['tile_code'],row)
NAMES={tile:next((c['text'] for c in d['commands'] if c['subcommand']==7),'') for tile,d in DEFS.items()}

BOTTOM_TILES=(46,37,192,126,42,120,45,63,53,194)
EDITOR_OPTIONS=dict(bottom=[dict(tile=t,name=NAMES[t]) for t in BOTTOM_TILES],upper=[dict(tile=0,name='None · 清空上层')]+[dict(tile=t,name=NAMES[t]) for t in DEFS if t not in BOTTOM_TILES and t not in (32,64,95,124) and NAMES[t]])

@lru_cache(maxsize=1024)
def actor_background(class_id,parameter):
    selected=select_background([r for r in BYT['records'] if r['opcode']==1],class_id,parameter)
    return selected['resource_id'] if selected else 194


class Game:
    def __init__(self,scenario=None):self.reset(scenario)
    def reset(self,scenario=None):
        self.scenario=scenario or getattr(self,'scenario',LEVELS[0]['id'])
        if self.scenario not in LEVEL_BY_ID:raise ValueError('未知关卡')
        self.rows=[row.copy() for row in LEVEL_BY_ID[self.scenario]['rows']]
        self.debug_resources={};self.debug_bottom={};self.special_underlays={};self.static_kinds={};self.debug_open_doors=False
        self.music_selector=getattr(self,'music_selector',None) or MusicSelector(GIN)
        level=LEVEL_BY_ID.get(self.scenario)
        self.music_group=int.from_bytes(bytes.fromhex(level['trailer'])[:2],'little') if level else 0
        self.music=self.music_selector.rotate(self.music_group)
        self.world=World(self.rows,BYT,GIN,project_graphics=True)
        self.graphic_record_counts={}
        self.cached_cells=None;self.cached_cell_version=-1
        self.static_graphics_version=0
        self.acquired_keys=set()
        self.audio_count=0
        self.actor_primary={id(vm):DEFS[self.rows[vm.position[1]][vm.position[0]]]['resource_id'] for _,vm in self.world.instances}
        self.world.initialize_new_display_slots();self.world.apply_collection_setting_slice(0)
        self.world.enable_map_rules(self.rows);self.world.schedule_map_load_objects()
        self.initial=self.world.advance_input_cycle();self.turn=0;self.revision=getattr(self,'revision',0)+1
        self.trajectory=dict(run=secrets.token_hex(16),level=self.scenario,start=list(self.world.player.position) if self.world.player else None,clicks=[],steps=[])
        self.solution_submitted=False
        self.diagnostic=None
        if not self.initial['complete']:self.diagnostic=self.initial.get('diagnostic')
        if getattr(self,'debug_shield',False):self.apply_debug_shield()
    def apply_debug_shield(self):
        player=self.world.player
        if not getattr(self,'debug_shield',False) or player is None:return
        # Test intervention: renew native protection counter/group and six event bits.
        player.fields[0]=11;player.mask &= ~63
        self.world.set_overlay(player.position,1)
    def toggle_debug_shield(self,enabled):
        self.debug_shield=bool(enabled)
        if self.debug_shield:self.apply_debug_shield()
        elif self.world.player is not None:
            self.world.player.fields[0]=0;self.world.player.mask |= 63
            self.world.set_overlay(self.world.player.position,0)
        self.revision+=1
    def debug_action(self,action):
        if action not in ('kill','fill','reveal','doors'):raise ValueError('未知调试操作')
        w=self.world;changed=0;detached=set()
        if action=='kill':
            for program,vm in w.instances:
                if program in (11,12,13) and not vm.disposed:w.dispose_object(vm);changed+=1
        else:
            for y,row in enumerate(self.rows):
                for x,_ in enumerate(row):
                    pos=(x,y);index=y*128+x;cls=w.classes[index];parameter=w.parameters[index]
                    if action=='fill' and cls==2 and parameter&14:
                        # Use the verified native completed-fill graphics.
                        resource=1364 if parameter&8 else 1368 if parameter&4 else 1928
                        w.parameters[index]=(parameter&~14) | (16512 if resource==1928 else 0)
                        w.write_class(pos,cls);w.resources[pos]=resource
                        self.debug_resources[pos]=resource
                        if resource==1364:self.special_underlays[pos]=1413
                    elif action=='reveal' and parameter&16:
                        w.parameters[index]=parameter&~16;w.write_class(pos,cls)
                    elif action=='doors' and (13<=cls<=26 or cls in (28,29)):
                        # Classes 23..26 are the four one-way door orientations.
                        cls=14 if cls in (14,19,20,21,22,25,26,29) else 13
                        w.parameters[index]=0;w.write_class(pos,cls);detached.add(pos)
                    elif action=='doors' and cls==12:
                        w.parameters[index]=parameter|64;w.write_class(pos,cls);detached.add(pos)
                    else:continue
                    changed+=1
            if detached and w.rule_instances is not None:
                w.rule_instances[:]=[i for i in w.rule_instances if i['position'] not in detached]
        if action=='doors':self.debug_open_doors=True
        self.cached_cell_version=-1;self.static_graphics_version+=1;self.revision+=1
        return changed
    def edit_tile(self,x,y,bottom,upper,revision):
        if revision!=self.revision:raise ValueError('状态已变化，请重新选择目标格')
        if not (0<=y<len(self.rows) and 0<=x<len(self.rows[y])):raise ValueError('目标格超出地图')
        if bottom not in BOTTOM_TILES or upper not in [o['tile'] for o in EDITOR_OPTIONS['upper']]:raise ValueError('请选择有效的上下层类型')
        w=self.world;pos=(x,y);index=y*128+x
        if w.player is not None and w.player.position==pos and upper:raise ValueError('人物所在格不能放置上层物体，请选择其他格')
        if w.pending_transition or self.diagnostic:raise ValueError('请重开关卡后再编辑')
        # Debug intervention; current instances and other cells keep their state.
        if w.classes[index]==5:w.collectible_count=max(0,w.collectible_count-1)
        for _,vm in list(w.objects.get(pos,[])):
            if vm is not w.player:w.dispose_object(vm)
        w.rule_instances[:]=[r for r in w.rule_instances if r['position']!=pos]
        self.debug_resources.pop(pos,None);self.special_underlays.pop(pos,None);self.static_kinds.pop(pos,None)
        base=DEFS[bottom];top=DEFS[upper] if upper else base
        self.rows[y][x]=upper or bottom;self.debug_bottom[pos]=bottom
        w.parameters[index]=base['parameter_raw'] | (top['parameter_raw'] if upper else 0)
        w.graphic_masks[y*w.graphic_map_size[0]+x]=base['last_byte_raw']
        w.write_class(pos,top['leading_bytes_raw'][1]);w.resources[pos]=top['resource_id']
        if upper and top['flags_raw']&2:w.collectible_count+=1
        branches=w.rule_links[top['offset']]
        if branches:w.rule_instances.insert(0,dict(position=pos,definition_offset=top['offset'],slot=branches[0]['slot'],dirty=False))
        program=top['byte_raw'] if upper else 255
        if 0<program<255:
            # Reuse the established BYT/GIN constructor, then attach the fresh object.
            template=World([[upper]],BYT,GIN,project_graphics=True)
            _,vm=template.instances[0];vm.position=pos;vm.host=w;vm.context=w.context
            w.instances.append((program,vm));w.objects.setdefault(pos,[]).append((program,vm))
            self.actor_primary[id(vm)]=top['resource_id']
            if id(vm) in template.graphical_instances:
                graphic=template.graphical_instances[id(vm)];w.projection.place(graphic,x,y)
                w.graphical_instances[id(vm)]=graphic;w.overlays[id(vm)]=template.overlays[id(vm)]
            if top['flags_raw']&4:
                result=vm.run()
                if result['reason']=='yield' and result.get('state') is not None:w.scheduler.request(vm,result['state'])
                elif result['reason'] not in ('yield','finished','disposed','end','object already disposed'):raise ValueError('对象初始化遇到未支持的程序状态：'+result['reason'])
            self.graphic_record_counts[id(vm)]=0
        self.cached_cell_version=-1;self.static_graphics_version+=1;self.revision+=1
        return dict(x=x,y=y,bottom=bottom,upper=upper)

    def state(self,pending_pixels=None):
        if not hasattr(self,"music_selector"):
            self.music_selector=MusicSelector(GIN)
            level=LEVEL_BY_ID.get(self.scenario)
            self.music_group=int.from_bytes(bytes.fromhex(level["trailer"])[:2],"little") if level else 0
            self.music=self.music_selector.rotate(self.music_group)
        w=self.world;cells=[]
        completed=bool(w.pending_transition and w.pending_transition['kind']==3 and w.pending_transition['mode']==0)
        for i in (1,2,3,4):
            if w.value_slots.get(i,0)>0:self.acquired_keys.add(i)
        needed_keys=[dict(slot=slot,color=color) for slot,color,tiles in
            ((1,'red',(104,196)),(2,'blue',(105,199)),(3,'green',(103,198)),(4,'yellow',(106,197)))
            if any(t in tiles for row in self.rows for t in row)]
        version=(len(w.map_changes),len(w.graphic_mask_changes),getattr(self,'static_graphics_version',0))
        for y,row in enumerate(self.rows if self.cached_cell_version!=version else []):
            line=[]
            for x,tile in enumerate(row):
                cls=w.classes[y*128+x];parameter=w.parameters[y*128+x]
                # Logical class updates override original static tile identity.
                label=NAMES[tile]
                if cls!=DEFS[tile]['leading_bytes_raw'][1]:label='Floor' if cls==2 else f'Class {cls}'
                if 0<DEFS[tile]['byte_raw']<255:label='Floor'
                resource=w.resources.get((x,y),194)
                if resource not in (1364,1368,1928) and any(not vm.disposed and id(vm) in w.graphical_instances for _,vm in w.objects.get((x,y),[])):resource=actor_background(cls,parameter)
                resource=getattr(self,'debug_resources',{}).get((x,y),resource)
                if cls==2 and resource==982:label='Hidden Floor'
                if label.startswith('Hidden ') and not parameter&16:label=label[7:]
                if getattr(self,'debug_open_doors',False) and cls in (13,14):label='Unlocked Door'
                if resource in (1928,1368,1364):label='Filled Exit' if resource==1364 and self.special_underlays.get((x,y))==596 else {1928:'Filled Water',1368:'Filled Lava',1364:'Filled Pit'}[resource]
                line.append(dict(x=x,y=y,name=label,cls=cls,parameter=parameter,resource=resource,mask=w.graphic_masks[y*w.graphic_map_size[0]+x] if w.graphic_masks is not None else 1,surface_kind=self.static_kinds.get((x,y)) if resource==w.resources.get((x,y)) else None,underlay_resource=self.special_underlays.get((x,y),1413 if resource==1364 else 194),base_resource=actor_background(2,parameter) if (x,y) in self.debug_bottom and resource not in (1364,1368,1928) else 194,empty=tile==32 and resource==1))
            cells.append(line)
        if self.cached_cell_version!=version:
            self.cached_cells=cells;self.cached_cell_version=version
        else:cells=self.cached_cells
        actors=[dict(program=p,x=vm.position[0],y=vm.position[1],occlusion_source=list((pending_pixels or {}).get(id(vm),())) or None,protection=vm.fields[0] if p==1 else 0,
                     pixel=list((pending_pixels or {}).get(id(vm),w.graphical_instances[id(vm)].position) if w.graphical_instances[id(vm)].action>=0 else w.graphical_instances[id(vm)].position) if id(vm) in w.graphical_instances else None,
                     resource=w.graphical_instances[id(vm)].resource if id(vm) in w.graphical_instances else 0,
                     primary=self.actor_primary[id(vm)],overlay=w.overlays[id(vm)].resource if id(vm) in w.overlays else None)
                for p,vm in w.instances if not vm.disposed and id(vm) in w.graphical_instances]
        return dict(cells=cells,actors=actors,turn=self.turn,revision=self.revision,scenario=self.scenario,
            music_group=self.music_group,music=self.music,debug_shield=getattr(self,'debug_shield',False),
            level_name=LEVEL_BY_ID[self.scenario]['name'],
            next_level=next((LEVELS[i+1]['id'] if i+1<len(LEVELS) and LEVELS[i+1]['id'].split('-')[0]==l['id'].split('-')[0] else None for i,l in enumerate(LEVELS) if l['id']==self.scenario),None),
            diamonds=w.collectible_count,keys={str(i):w.value_slots.get(i,0) for i in (1,2,3,4)},
            needed_keys=[] if getattr(self,'debug_open_doors',False) else needed_keys,acquired_keys=sorted(self.acquired_keys),completed=completed,
            transition=w.pending_transition,diagnostic=self.diagnostic,
            player=None if w.player is None else list(w.player.position))
    def click(self,x,y,revision):
        if revision!=self.revision:raise ValueError('状态已变化，请刷新后重试')
        w=self.world
        if not(0<=y<len(self.rows) and 0<=x<len(self.rows[y])):raise ValueError('格子超出边界')
        if self.diagnostic or w.player is None or w.pending_transition:return dict(frames=[],state=self.state(),message='本次测试已结束，请重新开始')
        kinds=commands(w.player.position,(x,y),0)
        if not kinds:return dict(frames=[],state=self.state(),message='请点击与人物同一行或同一列的格子')
        if getattr(self,'trajectory',None) is not None:self.trajectory['clicks'].append([x,y])
        start=w.player.position
        axis=0 if start[0]!=x else 1
        destination=(x,y)[axis]
        direction=1 if destination>start[axis] else -1
        frames=[];playback=[]
        for kind in kinds:
            trace_start=len(w.moves);position_start=list(w.player.position) if w.player else None
            w.input_queue.append(0,Command(kind))
            for _ in range(100):
                move_start=len(w.moves)
                pending_pixels={key:graphic.position for key,graphic in w.graphical_instances.items()}
                alive_monsters={id(vm):vm for p,vm in w.instances if p in (11,13) and not vm.disposed}
                self.apply_debug_shield()
                result=w.advance_input_cycle()
                self.apply_debug_shield()
                # User-confirmed original behavior: a killed alien/spider clears
                # the arrow path. Resume the adjacent arrow facing that cell.
                for monster in alive_monsters.values():
                    if not monster.disposed:continue
                    mx,my=monster.position
                    for ax,program in ((mx-1,4),(mx+1,3)):
                        arrow=w.find((ax,my))
                        if arrow and arrow[0]==program:w.enqueue_event(arrow[1],11)
                # Deliver every request once, before that cycle's animation.
                audio=w.audio_requests[getattr(self,'audio_count',0):]
                self.audio_count=len(w.audio_requests)
                # User-confirmed contact rule: moving arrows wake adjacent arrows.
                contacts=set()
                for move in w.moves[move_start:]:
                    if move['old']==move['new']:continue
                    target=w.find(tuple(move['new']))
                    if target is None or target[0] not in (3,4):continue
                    x0,y0=move['new']
                    for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                        other=w.find((x0+dx,y0+dy))
                        if other and other[0] in (3,4) and id(other[1]) not in contacts:
                            w.enqueue_event(other[1],11);contacts.add(id(other[1]))
                if not result['complete']:
                    self.diagnostic=result.get('diagnostic');break
                # Apply new VM51 writes once, then let GIN state0 scripts
                # choose resource frames and signed pixel displacements.
                for program,vm in w.instances:
                    count=self.graphic_record_counts.get(id(vm),0)
                    graphic=w.graphical_instances.get(id(vm))
                    for request in vm.graphics[count:]:
                        position=(request['x'],request['y'])
                        target_graphic=graphic if position==vm.position and not vm.disposed else None
                        if target_graphic is not None:
                            target_graphic.resource=request['resource_id']
                        else:
                            if vm.disposed and program in (11,12,13):self.static_kinds[position]='corpse'
                            else:self.static_kinds.pop(position,None)
                            previous=w.resources.get(position)
                            if request['resource_id']==1364 and previous in (1413,596):
                                # Executed Rock program writes structure then settled ball.
                                self.special_underlays[position]=previous
                            elif request['resource_id']!=1364:self.special_underlays.pop(position,None)
                            w.resources[position]=request['resource_id']
                            self.static_graphics_version=getattr(self,'static_graphics_version',0)+1
                    self.graphic_record_counts[id(vm)]=len(vm.graphics)
                for _ in range(240):
                    if not w.graphics_queue.nodes:break
                    w.advance_graphics(1,choose=lambda count:0)
                    w.advance_overlays(1)
                    frame=self.state(pending_pixels)
                    if audio:frame['audio']=audio;audio=[]
                    playback.append(frame)
                else:
                    self.diagnostic='图形队列超过240步，已停止';break
                if audio:playback.append(dict(self.state(),audio=audio))
                # 414170 resumes state2/3 before checking input, even with
                # empty input slots. Do not defer this work to another click.
                if not w.input_queue.head() and not w.scheduler.queues[2] and not w.scheduler.queues[3]:break
            else:self.diagnostic='行动调度超过100周期，已停止'
            if getattr(self,'debug_open_doors',False) and w.player is not None and w.pending_transition is None:
                px,py=w.player.position
                if w.classes[py*128+px]==12:
                    # Debug-only open exit also bypasses the native gem-count gate.
                    w.request_transition(3,0,0);w.dispose_object(w.player)
            self.turn+=1;self.revision+=1
            if getattr(self,'trajectory',None) is not None:
                self.trajectory['steps'].append(dict(step=self.turn,command=kind,start=position_start,end=list(w.player.position) if w.player else None,moves=[dict(start=m['old'],end=m['new']) for m in w.moves[trace_start:] if m.get('player')]))
            frames.append(self.state());playback.append(frames[-1])
            if self.diagnostic or w.pending_transition or w.player is None:break
            # Finish the original-program action, including its entire ice slide.
            # Sliding may reach/pass the target in one action; discard surplus
            # click-distance commands, while blocked actions still consume them.
            if start!=(x,y) and (w.player.position[axis]-destination)*direction>=0:break
        return dict(frames=frames,playback=playback,frame_ms=40,state=self.state(),message='行动完成')


@lru_cache(maxsize=1)
def solution_model():
    from web_solutions import model_fingerprint
    return model_fingerprint(ROOT)

@lru_cache(maxsize=1)
def optimal_solutions():
    path=ROOT/'web/assets/optimal-solutions.json'
    if not path.is_file():return {}
    return {r['level']:r for r in json.loads(path.read_text(encoding='utf-8'))['solutions'] if r['model']==solution_model()}

STORAGE=None
SESSIONS=SessionStore(lambda:Game('demo-1'))
DEBUG_SESSIONS=SessionStore(lambda:Game('level-1'))


def compact_playback(result):
    """Keep a full final state; only transmit changed maps in animation frames."""
    compact=dict(result);previous=None;playback=[]
    for frame in result.get('playback',[]):
        item=dict(frame);cells=item.get('cells')
        if cells is previous or cells==previous:item.pop('cells',None)
        previous=cells;playback.append(item)
    compact['playback']=playback
    compact['frames']=[{k:v for k,v in frame.items() if k!='cells'} for frame in result.get('frames',[])]
    return compact


class Handler(BaseHTTPRequestHandler):
    debug=False
    def route_mode(self):
        self.debug=self.path=='/debug' or self.path.startswith('/api/debug/')
        if self.debug and not getattr(self.server,'enable_debug',False):return False
        if self.path.startswith('/api/debug/'):self.path=self.path.replace('/api/debug/','/api/',1)
        return True
    def sessions(self):return DEBUG_SESSIONS if self.debug else SESSIONS
    def session_token(self):
        try:
            cookie=SimpleCookie(self.headers.get('Cookie',''))
            key='openrd_debug_session' if self.debug else 'openrd_session'
            return cookie[key].value if key in cookie else None
        except CookieError:return None
    def set_session_cookie(self,token,fresh):
        if fresh:self.session_cookie=f'{"openrd_debug_session" if self.debug else "openrd_session"}={token}; Path=/; HttpOnly; SameSite=Lax'+('; Secure' if getattr(self.server,'secure_cookies',False) else '')
    def profile(self):
        cookie=SimpleCookie(self.headers.get('Cookie',''))
        token,name,fresh=self.server.storage.profile(cookie['openrd_player'].value if 'openrd_player' in cookie else None)
        if fresh:self.profile_cookie=f'openrd_player={token}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax'+('; Secure' if getattr(self.server,'secure_cookies',False) else '')
        return token,name
    def decorate(self,game,token,name):
        state=game.state();state['player_name']=name
        state['progress']=self.server.storage.progress(token,LEVELS)
        state['debug']=self.debug
        if not self.debug:
            state['trajectory']=getattr(game,'trajectory',None)
            state['solution_submitted']=getattr(game,'solution_submitted',False)
            state['best_solution']=self.server.storage.best_solution(game.scenario,solution_model())
            optimal=optimal_solutions().get(game.scenario)
            state['optimal_steps']=optimal['steps'] if optimal else None
            if state['best_solution'] and optimal:state['best_solution']['optimal_proven']=state['best_solution']['steps']==optimal['steps']
        if self.debug:
            state['replay']=getattr(game,'replay_run',None) and {k:v for k,v in game.replay_run.items() if k!='targets'}
            state['progress']['unlocked']=[l['id'] for l in LEVELS]
            state['progress']['resume']=game.scenario
            state['leaderboard']=dict(entries=[]);state['completion_leaderboard']=dict(entries=[],own_completed=0)
            return state
        if state['completed']:
            state['leaderboard']=self.server.storage.ranking(token,game.scenario)
            state['completion_leaderboard']=self.server.storage.completion_ranking(token,LEVELS)
        return state
    def send(self,status,body,content_type):
        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Cache-Control','no-store')
        if len(body)>1024 and 'application/json' in content_type and 'gzip' in self.headers.get('Accept-Encoding',''):
            body=gzip.compress(body,compresslevel=1);self.send_header('Content-Encoding','gzip');self.send_header('Vary','Accept-Encoding')
        self.send_header('Content-Length',str(len(body)))
        if getattr(self,'session_cookie',None):self.send_header('Set-Cookie',self.session_cookie)
        if getattr(self,'profile_cookie',None):self.send_header('Set-Cookie',self.profile_cookie)
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if not self.route_mode():return self.send(404,b'Debug mode disabled','text/plain')
        if self.path in ('/','/debug'):
            html=(ROOT/'web/playtest.html').read_text(encoding='utf8')
            if self.debug:html=html.replace('const DEBUG_ENTRY=false','const DEBUG_ENTRY=true')
            return self.send(200,html.encode(),'text/html; charset=utf-8')
        if self.path=='/audio.js':return self.send(200,(ROOT/'web/audio.js').read_bytes(),'text/javascript; charset=utf-8')
        if self.path in ('/menu.js','/menu.css'):
            return self.send(200,(ROOT/'web'/self.path[1:]).read_bytes(),'text/javascript; charset=utf-8' if self.path.endswith('.js') else 'text/css; charset=utf-8')
        if self.path in ('/assets/ui/title.png','/assets/ui/company-logo.png','/assets/ui/level-map.png'):
            return self.send(200,(ROOT/'web'/self.path[1:]).read_bytes(),'image/png')
        if self.path=='/assets/video/corec.mp4':return self.send(200,(ROOT/'web/assets/video/corec.mp4').read_bytes(),'video/mp4')
        if self.path=='/api/hall-of-fame':
            if self.debug:return self.send(404,b'Not found','text/plain')
            levels=self.server.storage.hall_of_fame(LEVELS,solution_model())
            for level in levels:
                optimal=optimal_solutions().get(level['id']);level['optimal_steps']=optimal['steps'] if optimal else None
                if level['record']:level['record']['matches_optimal']=bool(optimal and level['record']['steps']==optimal['steps'])
            return self.send(200,json.dumps(dict(levels=levels),ensure_ascii=False).encode(),'application/json; charset=utf-8')
        if self.path=='/api/replay-options':
            if not self.debug:return self.send(404,b'Not found','text/plain')
            with self.sessions().acquire(self.session_token()) as (token,game,fresh):
                self.set_session_cookie(token,fresh)
                from debug_replay import options
                answers=options(game.scenario,self.server.storage)
            return self.send(200,json.dumps(dict(scenario=game.scenario,options=answers),ensure_ascii=False).encode(),'application/json; charset=utf-8')
        if self.path=='/api/solution':
            if self.debug:return self.send(404,b'Not found','text/plain')
            with self.sessions().acquire(self.session_token()) as (_,game,_):
                answer=self.server.storage.best_solution(game.scenario,solution_model(),include_route=True)
            return self.send(200,json.dumps(dict(solution=answer),ensure_ascii=False).encode(),'application/json; charset=utf-8')
        if self.path=='/api/editor-options':
            if not self.debug:return self.send(404,b'Not found','text/plain')
            return self.send(200,json.dumps(EDITOR_OPTIONS,ensure_ascii=False).encode(),'application/json; charset=utf-8')
        if self.path=='/api/levels':return self.send(200,json.dumps([dict(id=l['id'],number=l['number'],name=l['name'],series=l.get('series','演示关卡')) for l in LEVELS],ensure_ascii=False).encode(),'application/json; charset=utf-8')
        if self.path in ('/assets/sprites.json','/assets/sprites.png','/assets/shadows.png','/assets/masks.png'):
            return self.send(200,(ROOT/'web'/self.path.lstrip('/')).read_bytes(),'application/json' if self.path.endswith('.json') else 'image/png')
        if self.path=='/assets/audio.json':return self.send(200,(ROOT/'web/assets/audio.json').read_bytes(),'application/json')
        if self.path.startswith('/assets/audio/'):
            name=self.path[len('/assets/audio/'):]
            allowed={e['file'] for e in json.loads((ROOT/'web/assets/audio.json').read_text())['files']}
            if name in allowed:return self.send(200,(ROOT/'web/assets/audio'/name).read_bytes(),'audio/mp4')
        if self.path=='/api/state':
            try:
                with self.sessions().acquire(self.session_token()) as (token,game,fresh):
                    self.set_session_cookie(token,fresh);profile,name=self.profile();body=json.dumps(self.decorate(game,profile,name),ensure_ascii=False).encode()
            except SessionCapacityError as error:return self.send(503,json.dumps(dict(error=str(error)),ensure_ascii=False).encode(),'application/json; charset=utf-8')
            return self.send(200,body,'application/json; charset=utf-8')
        self.send(404,b'Not found','text/plain')
    def do_POST(self):
        if not self.route_mode():return self.send(404,b'Debug mode disabled','text/plain')
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>(2_000_000 if self.path=='/api/solution' else 4096):raise ValueError('Request too large')
            data=json.loads(self.rfile.read(size) or b'{}')
            if self.path not in ('/api/reset','/api/click','/api/save','/api/load','/api/name','/api/shield','/api/debug-action','/api/edit-tile','/api/solution','/api/replay-start','/api/replay-step','/api/replay-stop'):return self.send(404,b'Not found','text/plain')
            if self.path in ('/api/shield','/api/debug-action','/api/edit-tile','/api/replay-start','/api/replay-step','/api/replay-stop') and not self.debug:raise ValueError('仅调试入口可使用调试操作')
            if self.debug and self.path in ('/api/save','/api/load','/api/name','/api/solution'):raise ValueError('调试入口不写入普通存档、名字或排行榜')
            with self.sessions().acquire(self.session_token()) as (token,game,fresh):
                self.set_session_cookie(token,fresh)
                profile,name=self.profile()
                if self.path=='/api/click' and fresh:raise ValueError('会话不存在或已过期，请刷新页面重新开始')
                if not self.debug and self.path in ('/api/click','/api/save','/api/load') and game.scenario not in self.server.storage.progress(profile,LEVELS)['unlocked']:raise ValueError('请先通过前一关，再挑战本关')
                if getattr(game,'replay_run',None) and self.path not in ('/api/replay-step','/api/replay-stop'):
                    raise ValueError('请先停止重放，再进行其他操作')
                if self.path in ('/api/replay-start','/api/replay-step','/api/replay-stop'):
                    from debug_replay import replay_request
                    result=replay_request(game,self.path,data,self.server.storage)
                    if data.get('compact') is True:result=compact_playback(result)
                elif self.path=='/api/reset':
                    scenario=data.get('scenario')
                    if scenario is not None and scenario not in LEVEL_BY_ID:raise ValueError('请选择有效关卡')
                    if not self.debug and (scenario or game.scenario) not in self.server.storage.progress(profile,LEVELS)['unlocked']:raise ValueError('请先通过前一关，再挑战本关')
                    game.reset(scenario)
                    if not self.debug:self.server.storage.visit(profile,game.scenario)
                    result=dict(state=game.state(),frames=[])
                elif self.path=='/api/shield':
                    if not isinstance(data.get('enabled'),bool):raise ValueError('enabled 必须是布尔值')
                    game.toggle_debug_shield(data['enabled']);result=dict(frames=[],message='无限保护罩已开启' if data['enabled'] else '无限保护罩已关闭')
                elif self.path=='/api/debug-action':
                    count=game.debug_action(data.get('action'));result=dict(frames=[],message=f'调试操作完成：更新 {count} 项')
                elif self.path=='/api/edit-tile':
                    edited=game.edit_tile(int(data['x']),int(data['y']),int(data['bottom']),int(data['upper']),int(data['revision']));result=dict(frames=[],edited=edited,message='目标格已更新；重开关卡可恢复原图')
                elif self.path=='/api/click':
                    result=game.click(int(data['x']),int(data['y']),int(data['revision']))
                    if data.get('compact') is True:result=compact_playback(result)
                elif self.path=='/api/solution':
                    from web_solutions import verify_submission
                    route=verify_submission(game,data.get('trajectory'),Game)
                    accepted=self.server.storage.submit_solution(profile,game.scenario,game.turn,route,solution_model())
                    game.solution_submitted=True
                    result=dict(frames=[],solution=accepted,message='解法已提交：已更新本关最佳答案' if accepted['improved'] else '解法已提交')
                elif self.path=='/api/save':
                    self.server.storage.save(profile,game);result=dict(frames=[],message='本关存档已覆盖')
                elif self.path=='/api/load':
                    self.server.storage.load(profile,game);result=dict(frames=[],message='已读取本关存档')
                elif self.path=='/api/name':
                    name=self.server.storage.name(profile,data['name']);result=dict(frames=[],message='名字已保存')
                if not self.debug and game.state()['completed']:self.server.storage.score(profile,game.scenario,game.turn)
                result['state']=self.decorate(game,profile,name)
            self.send(200,json.dumps(result,ensure_ascii=False).encode(),'application/json; charset=utf-8')
        except (ValueError,KeyError,TypeError) as error:self.send(400,json.dumps(dict(error=str(error)),ensure_ascii=False).encode(),'application/json; charset=utf-8')
        except SessionCapacityError as error:self.send(503,json.dumps(dict(error=str(error)),ensure_ascii=False).encode(),'application/json; charset=utf-8')
    def log_message(self,*args):pass


