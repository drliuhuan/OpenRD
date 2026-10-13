"""0x4199B0 target expansion with mode argument zero, signed byte deltas."""

def commands(player,target,mode=0):
    if mode!=0:return []
    dx=((target[0]-player[0]+128)&255)-128
    dy=((target[1]-player[1]+128)&255)-128
    if dy==0:
        return [3]*dx if dx>0 else [4]*(-dx) if dx<0 else [6]
    if dx==0:return [2]*dy if dy>0 else [1]*(-dy)
    return []
