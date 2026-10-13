"""0x414253..4142AB type-5 target alignment gate; not click scheduling."""

def accepts_target(player, target, direction_mode):
    dx=player[0]-target[0]
    dy=player[1]-target[1]
    if direction_mode==4:return dx==0 or dy==0
    if direction_mode==8:return dx==0 or dy==0 or abs(dx)==abs(dy)
    return True
