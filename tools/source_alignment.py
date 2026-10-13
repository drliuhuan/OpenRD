"""Visual ISO timeline adapter; reads state and graphics metadata, never source VM."""
from resource_frames import signed16


class IsoVisualAlignment:
    def __init__(self, renderer, byt, gin, coordinate_tables=None):
        self.renderer=renderer
        self.objects={r['object_id']:r for r in gin['records'] if r['opcode']==37}
        self.by_program={r['byte_raw']:r['words_raw'][3]&255 for r in byt['records'] if r['opcode']==2}
        self.coordinates=coordinate_tables
        self.cursors={};self.resources={};self.paths={};self.aliases={};self.overlays={}
        self.transitions={(r['target_resource_id'],r['base_resource_id']):[v['resource_id'] for v in r['links']]
                          for r in gin['records'] if r['opcode']==39}
        for oid,obj in self.objects.items():
            following={c['values_raw'][0]:c['values_raw'][1] for c in obj['commands'] if c['subcommand']==1}
            waits={c['values_raw'][0] for c in obj['commands'] if c['subcommand']==2}
            cursor_meta={}
            for command in obj['commands']:
                if command['subcommand']!=2:continue
                wait,action,start=command['values_raw'];cursor=start;chain=[]
                while cursor not in waits and cursor not in chain and len(chain)<4096:
                    chain.append(cursor)
                    if cursor not in following:break
                    cursor=following[cursor]
                if not chain:continue
                group,selector,idle=self.role(oid,wait,action)
                source=renderer.objects.get(oid,{})
                target=next((c['values_raw'][2] for c in source.get('commands',[])
                             if c['subcommand']==2 and c['values_raw'][:2]==[wait,action]),None)
                if selector is not None:
                    target=next((c['values_raw'][2] for c in source.get('commands',[])
                                 if c['subcommand']==4 and c['values_raw'][:2]==[group,selector]),target)
                fallback=source['entries_raw'][target][2] if target is not None else None
                base=dict(object=oid,wait=wait,action=action,group=group,selector=selector,idle=idle,length=len(chain),fallback=fallback)
                self.paths[oid,wait,action]=chain
                for phase,entry in enumerate(chain):
                    meta=dict(base,phase=phase)
                    cursor_meta[entry]=meta
                    self.resources.setdefault(obj['entries_raw'][entry][2],[]).append(meta)
            self.cursors[oid]=cursor_meta
            source=renderer.objects.get(oid)
            if source:
                self.aliases[obj['base_resource_id']]=source['base_resource_id']
                old_waits=sorted(waits);new_waits=sorted({c['values_raw'][0] for c in source['commands'] if c['subcommand']==2})
                for i,wait in enumerate(old_waits):
                    if i<len(new_waits):self.aliases[obj['entries_raw'][wait][2]]=source['entries_raw'][new_waits[i]][2]
        # Explicit visual roots keyed by tile, not cross-version numeric IDs.
        definitions={r['tile_code']:r for r in renderer.definitions}
        for definition in byt['records']:
            if definition['opcode']!=1:continue
            target=definitions.get(definition['tile_code'])
            if target and target['leading_bytes_raw'][1]==definition['leading_bytes_raw'][1]:
                self.aliases[definition['resource_id']]=target['resource_id']
        old={r['resource_id']:r for r in gin['records'] if r['opcode']==36}
        # Old appearance slots became external theme wrappers. All old variants
        # map to the same source wrapper, whose theme is chosen explicitly.
        for _ in range(16):
            before=len(self.aliases)
            for rid,target in list(self.aliases.items()):
                r=old.get(rid);s=renderer.resources.get(target)
                if not r or not s:continue
                if r['subtype']==3:
                    for child in r.get('resource_references',[]):self.aliases.setdefault(child,target)
                if r['subtype']==s['subtype'] and r['subtype'] not in (1,3,10,12):
                    for child,destination in zip(r.get('resource_references',[]),s.get('resource_references',[])):
                        self.aliases.setdefault(child,destination)
                    if 'base_resource_id' in r and 'base_resource_id' in s:
                        self.aliases.setdefault(r['base_resource_id'],s['base_resource_id'])
            transitions={r['target_resource_id']:r for r in renderer.gin['records'] if r['opcode']==39}
            for r in gin['records']:
                if r['opcode']!=39:continue
                target=self.aliases.get(r['target_resource_id']);s=transitions.get(target)
                if not s:continue
                self.aliases.setdefault(r['base_resource_id'],s['base_resource_id'])
                refs=s['links']
                if refs:
                    for i,child in enumerate(r['links']):
                        j=round(i*(len(refs)-1)/max(1,len(r['links'])-1))
                        self.aliases.setdefault(child['resource_id'],refs[j]['resource_id'])
            if len(self.aliases)==before:break
        source_overlays={(r['object_id'],r['parameter_raw']):r['resource_references'] for r in renderer.gin['records'] if r['opcode']==42}
        for r in gin['records']:
            if r['opcode']!=42:continue
            refs=source_overlays.get((r['object_id'],r['parameter_raw']),[])
            for i,rid in enumerate(r['resource_references']):
                if refs:self.overlays[rid]=dict(resource=refs[i*len(refs)//len(r['resource_references'])],phase=i)
        # Parse literal graphical writes as bindings, without running either VM.
        # Match the ordinal within a program only when every coordinate operand
        # and the total request count agree. Conflicting bindings are rejected.
        from byt_vm_prefix import prefix
        programs={r['byte_raw']:r for r in renderer.byt['records'] if r['opcode']==2}
        literals={};self.literal_bindings=0
        def graphics(record):
            items=prefix(bytes.fromhex(record['payload_hex']))['instructions'];result=[]
            for i,item in enumerate(items):
                if item['opcode']!=51:continue
                if i<2 or items[i-2]['opcode']!=23 or items[i-1]['opcode'] not in (1,2):return None
                result.append((items[i-2]['operand_hex'],int.from_bytes(bytes.fromhex(items[i-1]['operand_hex']),'little')))
            return result
        for record in byt['records']:
            if record['opcode']!=2 or record['byte_raw'] not in programs:continue
            left=graphics(record);right=graphics(programs[record['byte_raw']])
            if left is None or right is None or [p for p,_ in left]!=[p for p,_ in right]:continue
            for (_,rid),(_,target) in zip(left,right):
                if rid not in old or target not in renderer.resources:continue
                if rid in literals and literals[rid]!=target:raise ValueError('Conflicting visual literal binding')
                literals[rid]=target;self.literal_bindings+=1
        self.aliases.update(literals)

    def role(self, oid, wait, action):
        source=self.renderer.objects.get(oid,{})
        macros={c['values_raw'][2]:c['values_raw'] for c in source.get('commands',[]) if c['subcommand']==4}
        groups={v[0] for v in macros.values()};group=next(iter(groups)) if len(groups)==1 else 0
        if oid==1:
            target=next((c['values_raw'][2] for c in source.get('commands',[])
                         if c['subcommand']==2 and c['values_raw'][:2]==[wait,action]),None)
            macro=macros.get(target)
            return (macro[0],macro[1],None) if macro else (group,None,None)
        # ISO's original action families, matched to the source group's IMC20
        # visual selector families. Source action opcodes are never executed.
        ranges={2:(11,20,11),3:(21,30,1),4:(31,70,1),5:(71,76,1),6:(81,100,1),7:(101,144,1),8:(145,172,1)}
        if oid==6 and 77<=action<=80:return group,None,action-77
        if oid in ranges:
            start,end,selector=ranges[oid]
            if start<=action<=end:return group,action-start+selector,None
        return group,None,None

    def observe(self, game, state, history):
        """Copy presentation metadata from the actual ISO graphical instances."""
        state=dict(state);state['actors']=[dict(a) for a in state['actors']]
        # An arrow temporarily sharing a corpse cell can leave the baseline's
        # cached cell projection as Floor. Read the actual ISO static graphic
        # buffer, without changing that cache, the map or the game rules.
        if game.static_kinds:
            overrides=[]
            for (x,y),kind in game.static_kinds.items():
                if kind=='corpse' and y<len(state['cells']) and x<len(state['cells'][y]):
                    rid=game.world.resources.get((x,y))
                    if rid is not None and (state['cells'][y][x]['resource']!=rid or state['cells'][y][x].get('surface_kind')!=kind):
                        overrides.append((x,y,rid,kind))
            if overrides:
                old=history.get('cells')
                if old and old[0] is state['cells'] and old[1]==overrides:state['cells']=old[2]
                else:
                    cells=[list(row) for row in state['cells']]
                    for x,y,rid,kind in overrides:cells[y][x]=dict(cells[y][x],resource=rid,surface_kind=kind)
                    history['cells']=(state['cells'],overrides,cells);state['cells']=cells
        for uid,(program,vm) in enumerate(game.world.instances):
            graphic=game.world.graphical_instances.get(id(vm))
            if not graphic:continue
            original=next((a for a in state['actors'] if a['program']==program and (a['x'],a['y'])==vm.position and 'uid' not in a),None)
            if original is None:
                # Cancelled visual nodes remain visible only until the ISO queue
                # itself removes them. This never resurrects the logical object.
                if not vm.disposed or not any(node[0] is graphic for node in game.world.graphics_queue.nodes):continue
                original=dict(program=program,x=vm.position[0],y=vm.position[1],pixel=list(graphic.position),resource=graphic.resource,
                              primary=0,overlay=None,occlusion_source=None,disposed=True)
                state['actors'].append(original)
            oid=self.by_program.get(program,0);candidate=self.cursors.get(oid,{}).get(graphic.cursor)
            previous=history.get(uid)
            if candidate:
                chain=self.paths[oid,candidate['wait'],candidate['action']]
                phase=max(0,candidate['phase']-1)
                expected=self.objects[oid]['entries_raw'][chain[phase]][2]
                if graphic.resource==expected:candidate=dict(candidate,phase=phase)
                else:candidate=None
            if not candidate and previous:
                candidates=self.resources.get(graphic.resource,[])
                candidate=next((m for m in candidates if m['object']==oid and m['action']==previous['action']),None)
            if not candidate:
                candidate=next((m for m in self.resources.get(graphic.resource,[]) if m['object']==oid),None)
            if candidate:history[uid]=dict(candidate)
            original.update(uid=uid,iso_object=oid,iso_visual=dict(candidate) if candidate else None)
        return state

    def resolve(self, rid, theme, meta=None):
        renderer=self.renderer
        if not meta and rid in self.aliases:return self.aliases[rid]
        if meta and meta.get('idle') is not None:
            obj=renderer.objects.get(meta['object'])
            return obj['entries_raw'][meta['idle']][2] if obj else 0
        candidates=[meta] if meta else self.resources.get(rid,[])
        for candidate in candidates:
            if not candidate or candidate.get('selector') is None:continue
            bank=renderer.themes.get(theme,{}).get('animations',{}).get((candidate['group'],candidate['selector']))
            if bank:
                phase=round(candidate['phase']*(len(bank)-1)/max(1,candidate['length']-1))
                return bank[phase]['resource']
            if candidate.get('fallback') is not None:return candidate['fallback']
        return self.aliases.get(rid)

    def index(self,x,y):
        t=self.coordinates
        if not t:return 0
        return t[0][((x&48)|(y&192))>>4]^t[1][(y&12)|(x&3)]^t[2][(x&12)|(y&3)]^t[3][(x>>4)&12]

    def expand_backgrounds(self, frames, initial):
        """The ISO Web's verified 41 terminal-matching chains, on copies only."""
        result=[];previous=initial
        for frame in frames:
            cells=frame.get('cells',previous);changes=[]
            if cells is not previous:
                for y,row in enumerate(cells):
                    for x,cell in enumerate(row):
                        old=previous[y][x] if y<len(previous) and x<len(previous[y]) else None
                        chain=self.transitions.get((old['resource'],cell['resource'])) if old else None
                        if chain and chain[-1]==cell['resource'] and old['resource']!=cell['resource']:
                            changes.append((x,y,chain))
            count=max([0]+[len(c) for _,_,c in changes])
            for i in range(count-1):
                shown=[list(row) for row in cells]
                for x,y,chain in changes:shown[y][x]=dict(shown[y][x],resource=chain[min(i,len(chain)-1)])
                item=dict(frame,cells=shown)
                if i:item.pop('audio',None)
                result.append(item)
            item=dict(frame)
            if count>1:item.pop('audio',None)
            result.append(item);previous=cells
        return result


def aligned_game_class(renderer, baseline_game):
    """Observe the baseline's snapshots; all game methods stay inherited."""
    class AlignedGame(baseline_game):
        def __init__(self,*args,**kwargs):
            self.source_visual_history={}
            super().__init__(*args,**kwargs)

        def state(self,pending_pixels=None):
            return renderer.alignment.observe(self,super().state(pending_pixels),self.source_visual_history)
    return AlignedGame
