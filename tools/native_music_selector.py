"""440910 grouped rotation and 4404F0 explicit selection; no MIDI device."""
class MusicSelector:
    def __init__(self,gin):
        self.tracks=[dict(id=r['values_raw'][0],mask=r['values_raw'][1],parameter=r['values_raw'][2],filename=r['text']) for r in gin['records'] if r['opcode']==11]
        self.counts=[sum(bool(t['mask']&(1<<g)) for t in self.tracks)&255 for g in range(16)]
        self.indices=[0]*16
        self.current=0

    def rotate(self,group,enabled=True,backend=True):
        if not enabled or not backend:return None
        if not 0<=group<16:raise ValueError('Only verified 16 music groups are supported')
        count=self.counts[group];index=self.indices[group]
        index=int(count!=0) if index==count else (index+1)&255
        self.indices[group]=index
        if not index:return None
        candidates=[t for t in self.tracks if t['mask']&(1<<group)]
        return candidates[index-1] if index<=len(candidates) else None

    def select(self,track,enabled=True,backend=True):
        track &= 65535
        if not enabled or not backend or track==self.current:return None
        result=next((t for t in self.tracks if t['id']==track),None)
        if result is not None:self.current=track
        return result

    def notify(self,notification):
        # 4406A0: only success branch reopens current id, other flags ignored.
        if notification!=1:return None
        return next((t for t in self.tracks if t['id']==self.current),None)
