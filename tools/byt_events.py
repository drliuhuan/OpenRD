"""Native 0x417000 / opcode 75 queue model; no scheduler emulation."""

def enqueue(queue, mask, event):
    event &= 255
    # x86 variable shifts use only the low five bits of the shift count.
    if not mask & (1 << ((event - 1) & 31)):
        return False
    queue[event] = (queue.get(event, 0) + 1) & 255
    return True

def consume(queue):
    if not queue:
        return -1
    event = min(queue)
    remaining = (queue[event] - 1) & 255
    if remaining:
        queue[event] = remaining
    else:
        del queue[event]
    return event or -1


