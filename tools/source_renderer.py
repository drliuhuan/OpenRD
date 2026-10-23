"""Local indexed GIN12 resource adapter. Never executes source game logic."""
import base64
import binascii
import json
import struct
import zlib
from pathlib import Path
from functools import lru_cache
from resource_frames import signed16, cdiv
from source_palette import EffectRegistry


def indexed_png(width, height, pixels, palette):
    if len(pixels) != width * height or len(palette) != 768:
        raise ValueError('Invalid indexed image')
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', binascii.crc32(kind + payload) & 0xffffffff)
    rows = b''.join(b'\0' + pixels[y*width:(y+1)*width] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B', width, height, 8, 3, 0, 0, 0))
            + chunk(b'PLTE', palette) + chunk(b'IDAT', zlib.compress(rows, 1)) + chunk(b'IEND', b''))


class ResourceRenderer:
    """Read-only renderer shared by games, with per-frame selector inputs.

    Uses the GIN's own RGB/effects and default base resources. Theme callbacks
    can be supplied through bindings without changing the game's VM or rules.
    """
    def __init__(self, gin):
        if gin['format'] != 'CCIg12':
            raise ValueError('Inline resource renderer requires CCIg12')
        self.gin = gin
        self.sprites = {r['sprite_id']:r for r in gin['records'] if r['opcode']==35}
        self.resources = {r['resource_id']:r for r in gin['records'] if r['opcode']==36}
        self.objects = {r['object_id']:r for r in gin['records'] if r['opcode']==37}
        palettes = [r['palette_rgb'] for r in gin['records'] if r['opcode']==8]
        if len(palettes)!=1:
            raise ValueError('A unique source RGB palette is required')
        self.palette = bytes(palettes[0])
        self.effects = EffectRegistry()
        for r in gin['records']:
            if r['opcode']==5 and 'effect_indices' in r:
                self.effects.register(bytes(r['effect_indices']))
        maps = [r for r in gin['records'] if r['opcode']==38 and r.get('subtype')==4]
        if len(maps)!=1:
            raise ValueError('A unique source map projection is required')
        values = maps[0]['values_raw']
        self.basis = tuple(map(signed16, values[2:6]))
        self.offset = tuple(map(signed16, values[6:8]))
        self.map_size=tuple(values[:2])
        self.layers=[c['values_raw'] for c in maps[0]['commands'] if c['subcommand']==4]
        self.groups={r['text'].lower():r['collection_id'] for r in gin['records'] if r['opcode']==44}
        self.themes={};self.theme_errors=[]
        self.definitions=[];self.by_program={}
        self.alignment=None
        self.cell_cache=[]
        self.static_cache=[]
        self.prepared_cache=[]
        self.calls_cache=[]
        self.payloads = {sid:bytes.fromhex(s['encoded_pixels_hex']) for sid,s in self.sprites.items()}

    def bind_definitions(self, byt):
        """Read visual class/program bindings only; no source VM execution."""
        self.definitions=[r for r in byt['records'] if r['opcode']==1]
        self.byt=byt
        self.visual_classes={r['leading_bytes_raw'][1] for r in self.definitions}
        self.by_program={r['byte_raw']:r['words_raw'][3]&255 for r in byt['records'] if r['opcode']==2}

    def bind_iso_graphics(self, byt, gin, coordinate_tables=None):
        from source_alignment import IsoVisualAlignment
        self.alignment=IsoVisualAlignment(self,byt,gin,coordinate_tables)
        self.cell_cache.clear();self.calls_cache.clear();self.prepared_cache.clear();self.static_cache.clear()

    @lru_cache(maxsize=1024)
    def background(self,cls,parameter):
        from byt_map_selector import select_background
        return select_background(self.definitions,cls,parameter)

    def render_iso_state(self, state, time=0, theme='', actor_actions=None, trace=False,view_size=None,camera=None):
        """Use ISO Game state as the sole logical input to a source asset skin.

        Class/parameter selects the source's visual definition; resource IDs are
        not assumed identical across versions. Unmapped classes are rejected.
        Actors use source program-to-object bindings and explicit action inputs.
        """
        if not self.definitions:raise ValueError('Source visual definitions were not bound')
        rows=next((rows for original,key,rows in self.cell_cache if original is state['cells'] and key==theme),None)
        if rows is None:
            rows=self.iso_cells(state['cells'],theme)
            self.cell_cache.append((state['cells'],theme,rows))
            if len(self.cell_cache)>4:self.cell_cache.pop(0)
        actors=[]
        for a in state['actors']:
            actor=dict(x=a['x'],y=a['y'],program=a['program'],object=self.by_program.get(a['program'],0),
                       action=(actor_actions or {}).get(a['program'],0),pixel=a.get('pixel'),occlusion_source=a.get('occlusion_source'),
                       uid=a.get('uid'),iso_visual=a.get('iso_visual'),disposed=a.get('disposed',False))
            if self.alignment:
                resource=self.alignment.resolve(a['resource'],theme,a.get('iso_visual'))
                if resource is not None:actor['resource']=resource
                overlay=self.alignment.overlays.get(a.get('overlay'))
                if overlay:actor['overlay']=overlay
            actors.append(actor)
        frame=self.render(dict(cells=rows,actors=actors,player=state.get('player')),time,theme=theme,trace=trace,view_size=view_size,camera=camera)
        frame['logical_source']='User ISO Game state; source BYT used for visual bindings only'
        return frame

    def iso_cells(self,cells,theme):
        rows=[]
        for row in cells:
            result=[]
            for cell in row:
                if cell.get('empty'):
                    result.append(dict(tile=32,resource=0,mask=0));continue
                if cell['cls'] not in self.visual_classes:
                    raise ValueError('Unmapped ISO visual class '+str(cell['cls']))
                definition=self.background(cell['cls'],cell['parameter'])
                resource=self.alignment.resolve(cell['resource'],theme) if self.alignment else None
                covered=bool(cell['parameter']&16 and (cell['resource'] in (982,984,2997,2998,3002) or cell.get('base_resource') in (982,984,2997,2998,3002)))
                result.append(dict(tile=definition['tile_code'] if definition['tile_code']!=32 else 0,resource=resource if resource is not None else definition['resource_id'],
                                   mask=cell.get('mask',definition['last_byte_raw']),covered=covered,
                                   corpse=cell.get('surface_kind')=='corpse',filled=cell['resource'] in (1364,1368,1928)))
            rows.append(result)
        return rows

    def load_themes(self, root):
        """Bind local THM/IMC files to namespaced resources, never to game rules."""
        from source_theme import parse
        import re
        root=Path(root);loaded={}
        def load(path):
            key=path.relative_to(root/'raw').as_posix()
            if key in loaded:return loaded[key]
            decoded=root/'decoded'/key
            parsed=parse((decoded if decoded.is_file() else path).read_bytes())
            ref=lambda r:(key,r['id']) if r['scope_raw']==0 else r['id']
            for r in parsed['records']:
                op=r['opcode']
                if op==2:
                    sid=(key,r['sprite_id']);s=dict(r,opcode=35,sprite_id=sid)
                    self.sprites[sid]=s;self.payloads[sid]=bytes.fromhex(s['encoded_pixels_hex'])
                elif 'resource_id' in r:
                    rid=(key,r['resource_id']);n=dict(resource_id=rid,opcode=36)
                    refs=[ref(v) for v in r.get('references',[])]
                    if op==3:n.update(subtype=1,frames=[dict(sprite_id=ref(c['reference']),offset_raw=c['offset_raw']) for c in r['components']])
                    elif op==4:n.update(subtype=2,base_resource_id=refs[0],sprite_reference=refs[1])
                    elif op==17:n.update(subtype=14,resource_references=refs)
                    elif op in (6,16):n.update(subtype=4 if op==6 else 16,resource_references=refs)
                    elif op in (7,8,9):n.update(subtype={7:17,8:19,9:18}[op],resource_references=refs,parameters_raw=[r['parameter_raw']])
                    elif op==11:n.update(subtype=6,base_resource_id=ref(r['base']),resource_references=refs,parameters_raw=r['parameters_raw'])
                    elif op==12:
                        node=r['expression']
                        # 4307A0/422130 store right at +10; 422A80 kind13
                        # follows +10 to the immediate display leaf.
                        while node['kind']==1:node=node['right']
                        n.update(subtype=13,resource_references=[(key,node['resource_id'])])
                    else:continue
                    self.resources[rid]=n
            pool={r['entry_id']:dict(r,resource=ref(r['reference'])) for r in parsed['records'] if r['opcode']==19}
            animations={}
            for record in parsed['records']:
                if record['opcode']!=20:continue
                selector,cursor=record['values_raw'];chain=[];seen=set()
                while cursor not in seen and len(chain)<4096:
                    seen.add(cursor);entry=pool[cursor];chain.append(entry)
                    if entry['control_raw']==3:break
                    if entry['control_raw']!=1:raise ValueError('Unsupported visual animation control')
                    cursor=entry['next_raw']
                else:raise ValueError('Visual animation cycle/depth')
                animations[selector]=chain
            loaded[key]=(parsed,{r['values_raw'][0]:(key,r['values_raw'][1]) for r in parsed['records'] if r['opcode']==13},animations)
            return loaded[key]
        for path in sorted((root/'raw').rglob('*.thm')):
            try:
                if path.stat().st_size>1024*1024:raise ValueError('THM exceeds 1 MiB')
                text=path.read_bytes().decode('latin1').replace('=',' ').replace(';',' ')
                # Native tokenizer discards an unterminated final word.
                words=re.findall(r'[^ \t\r\n]+(?=[ \t\r\n])',text)
                name=path.stem;index=0;bindings={};animations={}
                for key,value in zip(words[::2],words[1::2]):
                    key=key.lower()
                    if key=='name':name=value
                    elif key=='index':index=int(value)
                    elif key in self.groups:
                        if '/' in value or '\\' in value or value in ('.','..'):raise ValueError('Theme reference must be a local filename')
                        matches=[p for p in path.parent.iterdir() if p.name.lower()==value.lower()]
                        if len(matches)!=1:raise ValueError('Missing/ambiguous IMC '+value)
                        parsed,table,bank=load(matches[0])
                        if parsed['group_name'].lower()!=key:raise ValueError('Theme group mismatch')
                        bindings.update({(self.groups[key],selector):rid for selector,rid in table.items()})
                        animations.update({(self.groups[key],selector):chain for selector,chain in bank.items()})
                theme_id=path.relative_to(root/'raw').as_posix()
                self.themes[theme_id]=dict(id=theme_id,name=name,index=index,bindings=bindings,animations=animations)
            except (OSError,ValueError,KeyError) as exc:
                self.theme_errors.append(dict(path=path.relative_to(root).as_posix(),reason=str(exc)))

    def project(self, x, y):
        a,b,c,d = self.basis
        return a*x+c*y, b*x+d*y

    def components(self, rid, x=0, y=0, index=0, time=0, bindings=None, path=()):
        if not rid:
            return []
        if len(path)>=64 or rid in path:
            raise ValueError('Resource recursion cycle/depth')
        r = self.resources[rid]; subtype=r['subtype']; path=path+(rid,)
        recur=lambda target:self.components(target,x,y,index,time,bindings,path)
        refs=r.get('resource_references',[])
        if subtype==1:
            return [(self.sprites[f['sprite_id']], tuple(map(signed16,f['offset_raw'])),0,None) for f in r['frames']]
        if subtype==4:
            return recur(refs[signed16(index)%len(refs)]) if refs else []
        if subtype==19:
            width=signed16(r['parameters_raw'][0]);height=len(refs)//width if width>0 else 0
            if height<=0:raise ValueError('Invalid spatial resource selector')
            return recur(refs[(y%height)*width+x%width])
        if subtype==6:
            period,start,speed,_=map(signed16,r['parameters_raw'])
            if period<=0 or speed<=0:raise ValueError('Invalid time resource selector')
            phase=signed16(cdiv(signed16(index)+signed16(time),speed))%period
            return recur(refs[phase-start] if start<=phase<start+len(refs) else r['base_resource_id'])
        if subtype==10:
            base,group,selector=r['parameters_raw']
            target=(bindings or {}).get((group,selector),base)
            return recur(target)
        if subtype==14:
            return recur(refs[0])+recur(refs[1])
        if subtype==12:
            return recur(refs[0])
        if subtype==13:return recur(refs[0])
        if subtype==16:
            cells=(bindings or {}).get('$cells',[])
            mask=cells[y][x].get('mask',0) if 0<=y<len(cells) and 0<=x<len(cells[y]) else 0
            return recur(refs[mask%len(refs)]) if refs else []
        if subtype in (5,17,18):
            speed=r['parameters_raw'][0]
            if speed<=0:raise ValueError('Invalid theme time selector')
            phase=signed16(cdiv(signed16(time)+(signed16(index) if subtype in (5,17) else 0),speed))%len(refs)
            return recur(refs[phase])
        if subtype==2:
            return [(s,o,e,self.sprites[r['sprite_reference']]) for s,o,e,_ in recur(r['base_resource_id'])]
        raise ValueError('Unsupported source resource subtype '+str(subtype))

    @lru_cache(maxsize=32768)
    def animated(self,rid,theme):
        bindings=self.themes.get(theme,{}).get('bindings',{})
        def visit(rid,path=()):
            if not rid:return False
            if rid in path or len(path)>=64:return True
            r=self.resources.get(rid)
            if not r:return True
            subtype=r['subtype']
            if subtype in (5,6,17,18):return True
            if subtype==1:return False
            if subtype==10:
                base,group,selector=r['parameters_raw'];children=[bindings.get((group,selector),base)]
            else:children=r.get('resource_references',[])+([r['base_resource_id']] if 'base_resource_id' in r else [])
            return any(visit(child,path+(rid,)) for child in children)
        return visit(rid)

    def actor_resource(self, object_id, action=0, time=0):
        r=self.objects.get(object_id)
        if r is None:return 0
        entries=r['entries_raw']
        # Select the requested action's first resource, without inventing native
        # timing/randomness. The game's logical position remains authoritative.
        target=next((c['values_raw'][2] for c in r['commands']
                     if c['subcommand']==2 and c['values_raw'][1]==action),None)
        if target is not None and target<len(entries):
            for _ in range(max(0,min(64,time%64))):
                following=next((c['values_raw'][1] for c in r['commands']
                                if c['subcommand']==1 and c['values_raw'][0]==target),None)
                if following is None or following>=len(entries):break
                target=following
            return entries[target][2]
        return r['base_resource_id']

    def render(self, state, time=0, bindings=None, theme='',trace=False,view_size=None,camera=None):
        bindings=dict(self.themes[theme]['bindings'] if theme else (bindings or {}))
        bindings['$cells']=state['cells']
        cells=state['cells']; anchors=[self.project(x,y) for y,row in enumerate(cells) for x,c in enumerate(row) if c['tile']!=32]
        if not anchors:raise ValueError('Empty map')
        # Include all real sprite bounds, so tall objects are not clipped to cells.
        left=min(p[0] for p in anchors)-160; top=min(p[1] for p in anchors)-180
        width=max(p[0] for p in anchors)-left+180; height=max(p[1] for p in anchors)-top+180
        if width>8192 or height>8192 or width*height>64*1024*1024:raise ValueError('Rendered map exceeds surface budget')
        full_size=[width,height]
        view_camera=None
        if view_size:
            if len(view_size)!=2 or any(type(v) is not int or not 320<=v<=2048 for v in view_size):raise ValueError('Invalid resource viewport')
            vw,vh=min(width,view_size[0]),min(height,view_size[1])
            player=next((a for a in state['actors'] if a['program']==1 and not a.get('disposed')),None)
            px,py=(player.get('pixel') or self.project(player['x'],player['y'])) if player else self.project(*(state.get('player') or (0,0)))
            if camera is not None:
                if len(camera)!=2 or any(type(v) not in (int,float) or not -32768<=v<=32767 for v in camera):raise ValueError('Invalid resource camera')
                cx,cy=camera
                cx+=max(0,px-cx-vw*.35)+min(0,px-cx+vw*.35)
                cy+=max(0,py-cy-vh*.3)+min(0,py-cy+vh*.3)
            else:cx,cy=px,py
            view_camera=[round(cx),round(cy)]
            left=round(cx-vw/2);top=round(cy-vh*.6);width,height=vw,vh
        surface=bytearray(width*height);missing=set();drawn=0;calls=[];actor_trace=[];draw_trace=[]
        def add(x,y,rid,layer,rank=1,pixel=None,depth=None,index=None,selection_time=None,actor=None):
            position=pixel or self.project(x,y);depth=depth or position
            calls.append(dict(x=x,y=y,resource=rid,layer=layer,rank=rank,pixel=position,depth=depth,sequence=len(calls),
                              index=(self.alignment.index(x,y) if self.alignment else y*128+x) if index is None else index,
                              time=time if selection_time is None else selection_time,actor=actor))
        cached_calls=next((items for original,items in self.calls_cache if original is cells),None)
        for y,row in enumerate(cells if cached_calls is None else []):
            for x,c in enumerate(row):
                if c['tile']==32:continue
                for layer in self.layers:
                    bit=1<<(layer[0]-1)
                    if c.get('mask',0)&bit:
                        i=terrain_index(cells,x,y,bit)
                        if i+1<len(layer):add(x,y,layer[i+1],0 if layer[0]==1 else 1,0 if layer[0]==1 else .5)
                add(x,y,c['resource'],5 if c.get('covered') else 1,
                    .8 if c.get('corpse') else .75 if c.get('filled') else 1)
        if cached_calls is None:
            self.calls_cache.append((cells,list(calls)))
            if len(self.calls_cache)>4:self.calls_cache.pop(0)
        else:calls.extend(dict(c,time=time) for c in cached_calls)
        for actor in state['actors']:
            x,y=actor['x'],actor['y'];pixel=actor.get('pixel') or self.project(x,y)
            # Keep Hidden's source-cell depth anchor through entry and exit.
            source=actor.get('occlusion_source') or pixel
            a,b,c,d=self.basis;det=a*d-b*c
            sx=round((d*source[0]-c*source[1])/det);sy=round((a*source[1]-b*source[0])/det)
            covers=[(xx,yy) for xx,yy in ((sx,sy),(x,y)) if 0<=yy<len(cells) and 0<=xx<len(cells[yy]) and cells[yy][xx].get('covered')]
            cover=min(covers,key=lambda p:(self.project(*p)[1],self.project(*p)[0])) if covers else None
            depth=self.project(*cover) if cover else pixel
            rid=actor.get('resource',self.actor_resource(actor.get('object',0),actor.get('action',0),time))
            add(x,y,rid,3,pixel=pixel,depth=depth,index=0,actor=actor)
            if actor.get('overlay'):
                overlay=actor['overlay'];add(x,y,overlay['resource'],4,pixel=pixel,depth=depth,index=0,selection_time=overlay['phase']*4,actor=actor)
            actor_trace.append(dict(uid=actor.get('uid'),program=actor['program'],pixel=list(pixel),depth=list(depth),
                hidden_anchor=list(cover) if cover else None,resource=rid,visual=actor.get('iso_visual'),disposed=actor.get('disposed',False)))
        calls.sort(key=lambda c:(c['rank'],c['depth'][1],c['depth'][0],c['layer']))
        prepared=[];reusable=[];static_errors=[]
        cache_key=(theme,left,top,width,height)
        reusable_cached=next(((items,errors) for original,key,items,errors in self.prepared_cache if original is cells and key==cache_key),None) if not trace else None
        if reusable_cached:
            prepared.extend(reusable_cached[0]);missing.update(reusable_cached[1]);drawn+=len(reusable_cached[0])
        for call in calls:
            x,y,rid=call['x'],call['y'],call['resource']
            stable=call['actor'] is None and not self.animated(rid,theme)
            if stable and reusable_cached:continue
            try:components=self.components(rid,x,y,call['index'],call['time'],bindings)
            except (KeyError,ValueError,ZeroDivisionError) as exc:
                missing.add((str(rid),str(exc)))
                if stable:static_errors.append((str(rid),str(exc)))
                continue
            px,py=call['pixel']
            if trace and components:draw_trace.append(dict(x=x,y=y,resource=rid,rank=call['rank'],layer=call['layer'],pixel=list(call['pixel']),depth=list(call['depth']),actor=call['actor'].get('uid') if call['actor'] else None))
            for sprite,(dx,dy),effect,mask in components:
                position=(px-left+dx,py-top+dy);origin=tuple(map(signed16,sprite['origin_raw']))
                extent=mask or sprite
                ex,ey=((px-left,py-top) if mask else position)
                ox,oy=map(signed16,extent['origin_raw']);ew,eh=extent['dimensions']
                if ew<=0 or eh<=0 or ex-ox>=width or ey-oy>=height or ex-ox+ew<=0 or ey-oy+eh<=0:continue
                rectangle=(max(0,ex-ox),max(0,ey-oy),min(width-1,ex-ox+ew-1),min(height-1,ey-oy+eh-1))
                prepared.append((call,sprite,position,origin,effect,mask,rectangle))
                if stable:reusable.append(prepared[-1])
                drawn+=1
        if not reusable_cached and not trace:
            self.prepared_cache.append((cells,cache_key,reusable,static_errors))
            if len(self.prepared_cache)>4:self.prepared_cache.pop(0)
        prepared.sort(key=lambda item:(item[0]['rank'],item[0]['depth'][1],item[0]['depth'][0],item[0]['layer'],item[0]['sequence']))
        def paint(destination,item,clip):
                from source_pixels import draw_surface,draw_masked_surface
                call,sprite,position,origin,effect,mask,_=item;px,py=call['pixel']
                remap=self.effects.resolve(effect) if 0<effect<len(self.effects.tables) else None
                if mask:
                    draw_masked_surface((self.payloads[sprite['sprite_id']],*sprite['dimensions'],origin),
                        (self.payloads[mask['sprite_id']],*mask['dimensions'],tuple(map(signed16,mask['origin_raw']))),
                        destination,width,height,position,(px-left,py-top),clip,0,self.effects.sprite_shade(sprite),remap,in_place=True)
                else:
                    draw_surface(self.payloads[sprite['sprite_id']],*sprite['dimensions'],destination,width,height,
                        position,origin,clip,0,self.effects.sprite_shade(sprite),remap,in_place=True)
        clip=(0,0,width-1,height-1)
        if trace or width*height>4*1024*1024:
            for item in prepared:paint(surface,item,clip)
        else:
            static=[item for item in prepared if item[0]['actor'] is None]
            signature=tuple((item[1]['sprite_id'],item[2],item[4],item[5]['sprite_id'] if item[5] else None) for item in static)
            key=(theme,left,top,width,height,signature)
            cached=next((raw for original,k,raw in self.static_cache if original is cells and k==key),None)
            if cached is None:
                cached=bytearray(width*height)
                for item in static:paint(cached,item,clip)
                cached=bytes(cached);self.static_cache.append((cells,key,cached))
                if len(self.static_cache)>4:self.static_cache.pop(0)
            surface=bytearray(cached)
            regions=[]
            for item in prepared:
                if item[0]['actor'] is not None:regions.append(item[-1])
            # Merge overlap so shade operations are never applied twice.
            merged=[]
            for rectangle in regions:
                while True:
                    overlap=next((i for i,r in enumerate(merged) if not (rectangle[2]<r[0] or r[2]<rectangle[0] or rectangle[3]<r[1] or r[3]<rectangle[1])),None)
                    if overlap is None:break
                    r=merged.pop(overlap);rectangle=(min(r[0],rectangle[0]),min(r[1],rectangle[1]),max(r[2],rectangle[2]),max(r[3],rectangle[3]))
                merged.append(rectangle)
            for region in merged:
                l,t,r,b=region
                for y in range(t,b+1):surface[y*width+l:y*width+r+1]=bytes(r-l+1)
                # Repaint complete depth order inside the actor region, including
                # covers and shadows, rather than layering actors over a flat map.
                for item in prepared:
                    a,c,d,e=item[-1]
                    if not (d<l or r<a or e<t or b<c):paint(surface,item,region)
        png=indexed_png(width,height,bytes(surface),self.palette)
        result=dict(image='data:image/png;base64,'+base64.b64encode(png).decode('ascii'),
                    width=width,height=height,basis=list(self.basis),origin=[-left,-top],
                    components=drawn,missing=[dict(resource=r,reason=e) for r,e in sorted(missing)],
                    theme=theme,actors=actor_trace,camera=view_camera,full_size=full_size,hit_offset=[self.offset[0]/2,self.offset[1]/2],mode='Source RGB indexed software rendering')
        if trace:result['draw_order']=draw_trace
        return result


def load_renderers(root, bundle):
    root=Path(root);result={}
    sources=[(None,bundle)] if not bundle.get('datasets') else [
        (d['id'],json.loads((root/d['bundle']).read_text(encoding='utf-8'))) for d in bundle['datasets']]
    for key,b in sources:
        prefix=Path(next(d['bundle'] for d in bundle['datasets'] if d['id']==key)).parent.parent if key else Path('.')
        if b.get('gin'):
            gin=json.loads((root/prefix/b['gin']).read_text(encoding='utf-8'))
            if gin['format'] in ('CCIg11','CCIg12'):
                if gin['format']=='CCIg11':
                    from source_legacy_renderer import LegacyRenderer
                    result[key]=LegacyRenderer(gin,root/prefix)
                else:result[key]=ResourceRenderer(gin)
                result[key].bind_definitions(json.loads((root/prefix/b['byt']).read_text(encoding='utf-8')))
                result[key].load_themes(root/prefix)
    return result


def terrain_index(cells,x,y,bit):
    def has(dx,dy):
        yy,xx=y+dy,x+dx
        return 0<=yy<len(cells) and 0<=xx<len(cells[yy]) and bool(cells[yy][xx].get('mask',0)&bit)
    n=sum(b for dx,dy,b in ((0,-1,1),(0,1,2),(1,0,4),(-1,0,8)) if has(dx,dy))
    for value,diagonal,result in ((5,(1,-1),16),(6,(1,1),17),(9,(-1,-1),21),(10,(-1,1),22)):
        if n==value and not has(*diagonal):return result
    for value,offset,diags in ((7,17,((1,-1),(1,1))),(11,22,((-1,-1),(-1,1))),
            (13,25,((1,-1),(-1,-1))),(14,28,((1,1),(-1,1))),(15,31,((1,-1),(-1,-1),(1,1),(-1,1)))):
        if n==value:
            missing=sum(1<<i for i,d in enumerate(diags) if not has(*d))
            if missing:return offset+missing
    return n
