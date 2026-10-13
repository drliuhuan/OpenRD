"""Map-backed VM reads, movement and optional explicit graphical updates."""
import json
import hashlib
from pathlib import Path
from byt_vm_core import Core,Context,word,EngineStateUnavailable
import rdtool

class World:
    def __init__(self, rows, byt, gin=None, initial_graphics=False, project_graphics=False):
        self.classes=bytearray(128*128)
        self.parameters=[0]*(128*128)
        self.objects={}
        self.instances=[]
        self.player=None
        self.load_runnable=[]
        self.context=Context()
        # BYT top-level 3/4/5 -> native map C00A/C00B/C026.
        settings={r['opcode']:r['bytes_raw'][0] for r in byt['records'] if r['opcode'] in (3,4,5)}
        self.command_event=settings.get(3,0)
        self.target_event=settings.get(4,0)
        self.direction_mode=settings.get(5,0)
        self.current_command=0 # Explicit input probe; native queue not simulated.
        from byt_input_queue import InputQueue
        self.input_queue=InputQueue()
        self.load_input_cleanup_pending=False
        self.command_records=[]
        self.value_slots={}
        self.settings={}
        self.disposals=[]
        self.transition_requests=[]
        self.pending_transition=None
        self.delayed_transition=None
        self.value_changes=[]
        self.rule_instances=None
        self.schedule_requests=[]
        self.scheduler=None
        self.global_counter=0 # Explicit initial value; native save/load not modeled.
        self.counter_changes=[]
        self.collectible_count=0
        self.collectible_changes=[]
        self.moves=[]
        self.audio_requests=[]
        self.map_changes=[]
        self.graphical_instances={}
        self.graphic_masks=None
        self.graphic_mask_changes=[]
        self.graphic_rebuild_requests=[]
        self.overlays={}
        self.graphics_queue=None
        self.projection=None
        if project_graphics:
            if gin is None:raise ValueError('Projection requires GIN')
            from gin_projection import Projection
            self.projection=Projection.from_gin(gin)
        if initial_graphics and gin is None:
            raise ValueError('Initial graphics requires GIN')
        if gin is not None:
            from gin_graphics_state import Archetype,Instance
            from gin_graphics_queue import GraphicsQueue
            archetypes={r['object_id']:Archetype(r) for r in gin['records'] if r['opcode']==37}
            self.graphics_queue=GraphicsQueue()
            graphic_map=next(r for r in gin['records'] if r['opcode']==38)
            self.graphic_map_size=tuple(graphic_map['values_raw'][:2])
            if graphic_map['commands']:
                self.graphic_masks=bytearray(self.graphic_map_size[0]*self.graphic_map_size[1])
        self.width=max(map(len,rows),default=0)
        # Native 0x413F80 counts row markers; 0x4140EA increments once more.
        self.height=len(rows)+1
        self.resources={}
        self.deferred=[]
        definitions={}
        self.definitions=[r for r in byt['records'] if r['opcode']==1]
        for r in byt['records']:
            if r['opcode']==1:definitions.setdefault(r['tile_code'],r)
        programs={r['byte_raw']:r for r in byt['records'] if r['opcode']==2}
        for y,row in enumerate(rows):
            if y>=128 or len(row)>128:raise ValueError('Map exceeds native 128x128 grid')
            for x,tile in enumerate(row):
                if tile not in definitions:raise ValueError(f'Unknown map tile {tile}')
                d=definitions[tile];index=y*128+x
                if self.graphic_masks is not None:
                    self.graphic_masks[y*self.graphic_map_size[0]+x]=d['last_byte_raw']
                if d['flags_raw']&2:self.collectible_count=word(self.collectible_count+1)
                self.classes[index]=d['leading_bytes_raw'][1]
                self.parameters[index]=d['parameter_raw']
                self.resources[x,y]=d['resource_id']
                if 0<d['byte_raw']<255:
                    p=programs[d['byte_raw']]
                    vm=Core(bytes.fromhex(p['payload_hex']),mask=p['words_raw'][0]|p['words_raw'][1]<<16,
                            call_capacity=p['words_raw'][4],position=(x,y),
                            fields=list(map(word,d['words_raw']))+[0,0],host=self,context=self.context)
                    self.objects.setdefault((x,y),[]).append((d['byte_raw'],vm))
                    self.instances.append((d['byte_raw'],vm))
                    if d['flags_raw']&1:self.player=vm
                    if d['flags_raw']&4:self.load_runnable.append(vm)
                    if gin is not None:
                        archetype_id=p['words_raw'][3]&255
                        if archetype_id:
                            graphic=Instance(archetypes[archetype_id],action=0 if initial_graphics else -1)
                            self.graphical_instances[id(vm)]=graphic
                            from gin_overlay import Overlay
                            groups={r['parameter_raw']:r['resource_references'] for r in gin['records']
                                    if r['opcode']==42 and r['object_id']==archetype_id}
                            self.overlays[id(vm)]=Overlay(groups)
                            if self.projection:self.projection.place(graphic,x,y)
                            if initial_graphics:
                                self.graphics_queue.enqueue(graphic)

    def find(self,position):
        if any(v>=128 for v in position):return None
        objects=self.objects.get(position,[])
        return objects[0] if objects else None

    def move(self,vm,delta,action):
        old=vm.position
        new=tuple(max(0,min(old[j]+delta[j],(self.width,self.height)[j]-1)) for j in (0,1))
        # A requested nonzero delta re-inserts even if clamping leaves position unchanged.
        if any(delta):
            source=self.objects[old]
            index=next(n for n,item in enumerate(source) if item[1] is vm)
            obj=source.pop(index)
            if not source:del self.objects[old]
            self.objects.setdefault(new,[]).append(obj)
            vm.position=new
        self.moves.append(dict(old=list(old),new=list(vm.position),delta=list(delta),action=action,player=vm is self.player,
                               scope='Logical relocation and graphical transition request; animation not executed'))
        if self.graphics_queue is not None and id(vm) in self.graphical_instances:
            graphic=self.graphical_instances[id(vm)]
            if self.projection:self.projection.place(graphic,*vm.position)
            self.graphics_queue.request(graphic,action)

    def advance_graphics(self,steps,choose=None):
        if self.graphics_queue is None:
            raise ValueError('GIN graphical model was not enabled')
        return self.graphics_queue.advance(steps,choose=choose)

    def set_overlay(self,position,state):
        target=self.find(position)
        if target is None:return
        overlay=self.overlays.get(id(target[1]))
        if overlay is None:raise ValueError('Overlay operation requires enabled GIN graphics')
        overlay.select(state)

    def advance_overlays(self,steps):
        # Explicit update only: native map's separate overlay-list order/timer
        # is not implied by this helper.
        for overlay in self.overlays.values():overlay.advance(steps)

    def audio_request(self,opcode,sound):
        # Trace only: no audio device, suppression flag or playback scheduler.
        self.audio_requests.append(dict(opcode=opcode,sound_id=sound,
                                        native_argument=65535 if opcode==88 else 0 if opcode==89 else None))

    def send_event(self,position,event):
        from byt_events import enqueue
        target=self.find(position)
        if target is None:return
        vm=target[1]
        if not vm.mask & (1<<((event-1)&31)):return
        self.enqueue_event(vm,event)
        self.schedule_requests.append(dict(position=list(position),program_id=target[0],state=1))
        if self.scheduler is not None:self.scheduler.request(vm,1)

    def enqueue_event(self,vm,event):
        from byt_events import enqueue
        accepted=enqueue(vm.events,vm.mask,event)
        if accepted and self.scheduler is not None:self.scheduler.raise_state(vm,3)
        return accepted

    def drain_deferred(self,suppressed=False):
        delivered=[]
        while self.deferred:
            event=self.deferred.pop(0)
            target=None if suppressed else self.find((event['x'],event['y']))
            accepted=False if target is None else self.enqueue_event(target[1],event['event'])
            delivered.append(dict(**event,accepted=accepted,suppressed=suppressed))
        return delivered

    def enable_scheduler(self):
        from byt_scheduler import Scheduler
        self.scheduler=Scheduler()
        # No automatic initialization states or events are assumed.
        return self.scheduler

    def schedule_map_load_objects(self):
        s=self.enable_scheduler()
        for vm in self.load_runnable:s.request(vm,1)
        return s

    def mark_load_input_cleanup(self):
        #403EA7 sets4517BC;4042AD consumes it only after graphics/end gates.
        self.load_input_cleanup_pending=True

    def apply_load_input_cleanup(self):
        #4042B8 calls414730(slot,0,1) for all four slots: remove all heads.
        # Explicit call means the caller has reached this main-loop gate.
        if not self.load_input_cleanup_pending:return False
        self.load_input_cleanup_pending=False
        for slot in self.input_queue.slots:slot.clear()
        return True

    def advance_input_cycle(self,limit=1000):
        """Researched 414170 input/scheduler phase, excluding later map rules."""
        if self.scheduler is None:raise ValueError('Scheduler must be explicitly enabled')
        audio_start=len(self.audio_requests)
        from gin_target_alignment import accepts_target
        from byt_events import enqueue
        s=self.scheduler
        if self.rule_instances is not None:
            for instance in self.rule_instances:instance['dirty']=False
        player=self.player
        consumed=[]
        if s.queues[2]:s.promote(2)
        elif s.queues[3]:s.promote(3)
        else:
            woke=False
            for slot in range(4):
                self.input_queue.active=slot
                head=self.input_queue.head()
                if head is None:continue
                if head.kind==5 and player is not None and not accepts_target(player.position,(head.x,head.y),self.direction_mode):
                    self.input_queue.slots[slot].clear()
                    continue
                if not woke:s.wake_waiting();woke=True
                if player is not None and s.state(player)==0:
                    if head.kind!=5:self.record_command()
                    event=self.target_event if head.kind==5 else self.command_event
                    if head.kind!=5 or event>0:self.enqueue_event(player,event)
                    s.request(player,1)
                consumed.append(slot)
        # 414321 resets map+C024 to zero before runnable execution.
        self.input_queue.active=0
        reports=[]
        for _ in range(limit):
            entry=s.run_one()
            if entry is None:break
            vm,stop=entry
            program=next(program for program,item in self.instances if item is vm)
            reports.append(dict(program_id=program,stop=stop,position=list(vm.position)))
            if stop['reason']!='yield':
                return dict(complete=False,phase='input/scheduler',executions=reports,diagnostic=stop)
        else:return dict(complete=False,phase='input/scheduler',executions=reports,diagnostic='execution budget exceeded')
        for slot in consumed:
            self.input_queue.active=slot
            self.input_queue.pop()
        self.input_queue.active=0
        deferred=self.drain_deferred()
        rules=[] if self.rule_instances is None else self.evaluate_map_rules()
        return dict(complete=True,phase='input/scheduler, deferred delivery and optional map rules',executions=reports,consumed_slots=consumed,deferred=deferred,rules=rules,
                    audio_batch=self.audio_requests[audio_start:])

    def command_type(self):
        head=self.input_queue.head()
        return head.kind if head is not None else self.current_command

    def record_command(self):
        head=self.input_queue.head()
        kind=0 if head is None else head.kind
        # Trace opaque types too; native 0/5 advances over unspecified bytes.
        if 7<=kind<=11:return
        self.command_records.append(dict(kind=kind,character={1:'n',2:'s',3:'e',4:'w',6:'p'}.get(kind)))

    def set_value(self,index,value):
        # 414A30 -> 406060 writes global slot A0+index*4 and marks
        # dependent map-rule nodes. Rule evaluation is outside this host.
        self.value_slots[index]=value
        self.value_changes.append(dict(index=index,value=value,dependent_rules_pending=True))
        if self.rule_instances is not None:
            for instance in self.rule_instances:
                if instance['slot']==index:instance['dirty']=True

    def enable_map_rules(self,rows):
        from byt_map_rules import linked_rules
        self.rule_links=linked_rules(self.definitions)
        definitions={}
        for d in self.definitions:definitions.setdefault(d['tile_code'],d)
        self.rule_instances=[]
        for y,row in enumerate(rows):
            for x,tile in enumerate(row):
                d=definitions[tile];branches=self.rule_links[d['offset']]
                if branches:self.rule_instances.insert(0,dict(position=(x,y),definition_offset=d['offset'],slot=branches[0]['slot'],dirty=False))

    def initialize_new_display_slots(self):
        # 428360 constructor zeroes32 dwords; level/save overrides not assumed.
        self.value_slots={index:0 for index in range(32)}

    def reset_display_value_slots(self):
        # 429320 clears existing display slots, without 414A30 rule notification.
        self.value_slots.update({index:0 for index in range(32)})
        return dict(display_dirty=True,display_134=0,display_138=0)

    def apply_common_load_reset_slice(self):
        # Explicit partial effects of403C56 and403E7A, not full403AE0.
        # Calls between them and subsequent slot overrides remain unresolved.
        effect=self.reset_display_value_slots()
        self.global_counter=0
        return dict(effect,global_counter=0,scope='explicit reset slice; not complete level initialization')

    def evaluate_map_rules(self):
        if self.rule_instances is None:raise ValueError('Map rules must be explicitly enabled')
        from byt_map_rules import first_match
        pending=[i for i in self.rule_instances if i['dirty']]
        missing=[i['slot'] for i in pending if i['slot'] not in self.value_slots]
        if missing:raise ValueError(f'Uninitialized rule value slots: {missing}')
        results=[]
        for instance in pending:
            instance['dirty']=False
            branch=first_match(self.rule_links[instance['definition_offset']],self.value_slots[instance['slot']])
            if branch is None:continue
            x,y=instance['position']
            self.parameters[y*128+x]=branch['parameter']
            if branch['next_definition_offset'] is not None:instance['definition_offset']=branch['next_definition_offset']
            if branch['sound_id']:self.audio_request(89,branch['sound_id'])
            self.write_class((x,y),branch['class_id'])
            for event in branch['events']:
                target=self.find(((x+event['dx'])&255,(y+event['dy'])&255))
                if target is not None:self.enqueue_event(target[1],event['event'])
            results.append(dict(position=[x,y],branch_offset=branch['offset'],definition_offset=instance['definition_offset']))
        return results

    def adjust_counter(self,delta):
        raw=(self.global_counter+delta)&0xffffffff
        self.global_counter=raw-0x100000000 if raw>=0x80000000 else raw
        self.counter_changes.append(dict(delta=delta,value=self.global_counter,display_dirty=True))

    def adjust_collectibles(self,delta):
        self.collectible_count=word(self.collectible_count+delta)
        self.collectible_changes.append(dict(value=self.collectible_count,display_138=self.collectible_count,display_dirty=True))

    def get_value(self,index):
        if index not in self.value_slots:raise EngineStateUnavailable(f'Uninitialized display value slot: {index}')
        return self.value_slots[index]

    def get_setting(self,index):
        #434580: signed word bounds0..19; unknown in-range config must stop.
        index=word(index)
        if not 0<=index<20:return 0
        if index not in self.settings:raise EngineStateUnavailable(f'Uninitialized engine setting: {index}')
        return self.settings[index]

    def apply_collection_setting_slice(self, auxiliary_pointer):
        """403BA0..403BC0: explicit collection+E3C, not an assumed loader."""
        self.settings[4]=int(bool(auxiliary_pointer & 0xffffffff))
        return self.settings[4]

    def request_transition(self,kind,mode,delay):
        #138 ->405DD0 always clears all inputs; positive unsignedword delay
        # defers UI/collection effects. Record the request, do not guess mode.
        for slot in range(4):self.input_queue.remove_heads(slot,False,True)
        request=dict(kind=kind&255,mode=mode&255,delay=delay&65535,
                     scope='Native request fields and input clearing; UI/save/level change not executed; timer requires explicit advance')
        self.pending_transition=request
        self.transition_requests.append(request.copy())
        if request['delay']:
            self.delayed_transition=request.copy()

    def advance_transition_timer(self, tick_word):
        """404161..40419F: at most one decrement per explicit main-loop call."""
        delayed=self.delayed_transition
        if delayed is None or not delayed['delay'] or not (tick_word & 65535):
            return None
        delayed['delay']=(delayed['delay']-1)&65535
        if delayed['delay']:
            return None
        self.request_transition(delayed['kind'],delayed['mode'],0)
        return self.pending_transition.copy()

    def clear_graphic_layer_bit(self,position,bit):
        #405D90 computes an8-bit mask;42F510 updates layer byte through42EB00.
        # Resource-tree rebuild side effects are queued, not silently rendered.
        if self.graphic_masks is None:
            raise EngineStateUnavailable('Graphical map layer buffer was not enabled')
        mask=(1<<((bit-1)&31))&255
        if not mask:return
        x,y=position;index=word(self.graphic_map_size[0]*y+x)
        if not 0<=index<len(self.graphic_masks):
            raise EngineStateUnavailable('Native graphical layer access would be out of bounds')
        old=self.graphic_masks[index];new=old&~mask
        if new==old:return
        self.graphic_masks[index]=new
        change=dict(position=list(position),old_mask=old,new_mask=new,bit=bit)
        self.graphic_mask_changes.append(change)
        self.graphic_rebuild_requests.append(dict(change,scope='42EB00 graphical neighbor/resource rebuild pending'))

    def dispose_object(self,vm):
        if vm.disposed:return
        position=vm.position
        entries=self.objects.get(position,[])
        entries[:]=[item for item in entries if item[1] is not vm]
        if not entries:self.objects.pop(position,None)
        if self.scheduler is not None:self.scheduler.remove(vm)
        vm.events.clear();vm.returns.clear();vm.disposed=True
        if self.player is vm:self.player=None
        if self.graphics_queue is not None and id(vm) in self.graphical_instances:
            self.graphics_queue.cancel(self.graphical_instances[id(vm)])
        self.write_class(position,self.classes[position[1]*128+position[0]])
        self.disposals.append(dict(position=list(position),scope='Logical removal and graphical cancellation; native memory pool/render tree cleanup not modeled'))

    def write_parameter_bit(self,position,bit,enabled):
        x,y=position
        if not(0<=x<128 and 0<=y<128):return
        index=y*128+x;mask=(1<<((bit-1)&31))&65535
        old=self.parameters[index]
        self.parameters[index]=(old|mask) if enabled else (old&~mask)
        # Native always notifies4149F0, even when the bit did not change.
        self.write_class(position,self.classes[index])
        self.map_changes[-1].update(old_parameter=old,new_parameter=self.parameters[index])

    def expand_target(self,target,mode):
        from byt_target_commands import commands
        from byt_input_queue import Command
        player=self.player
        if player is None:raise ValueError('Target expansion requires player')
        for kind in commands(player.position,target,mode):
            self.input_queue.prepend(Command(kind,0,0,1))

    def write_class(self,position,class_id):
        x,y=position
        if not (0<=x<128 and 0<=y<128):return
        index=y*128+x
        old=self.classes[index]
        self.classes[index]=class_id&255
        selected=None
        # 44 clips against 128; 414850 separately clips to loaded dimensions.
        if x<self.width and y<self.height:
            from byt_map_selector import select_background
            selected=select_background(self.definitions,self.classes[index],self.parameters[index])
            if selected is not None:self.resources[position]=selected['resource_id']
        self.map_changes.append(dict(position=list(position),old_class=old,new_class=self.classes[index],
                                     definition_offset=None if selected is None else selected['offset'],
                                     resource_id=None if selected is None else selected['resource_id'],
                                     tile_code=None if selected is None else selected['tile_code']))

    def read(self,opcode,position,bit=None):
        x,y=position
        if x>=128 or y>=128:return 0
        if opcode==38:return self.classes[y*128+x]
        if opcode==46:return int(bool(self.parameters[y*128+x] & (1<<((bit-1)&31))))
        obj=self.find(position)
        if not obj:return 0
        if opcode==32:return obj[0]
        if opcode==39:return obj[1].fields[0]
        raise ValueError(f'Unsupported host query {opcode}')

    def defer(self,position,event):
        # Native opcode 72 forwards wrapped byte coordinates without grid clipping.
        self.deferred.append(dict(x=position[0]&255,y=position[1]&255,event=event&255))

