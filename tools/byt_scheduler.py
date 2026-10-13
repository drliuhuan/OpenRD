"""Native416A40 priority transitions,416F20 wakeup,4170B0 runnable pump."""

class Scheduler:
    priorities=(0,4,3,2,1)

    def __init__(self):
        self.queues={state:[] for state in range(1,5)}
        self.states={}

    def state(self,vm):return self.states.get(id(vm),0)

    def remove(self,vm):
        state=self.state(vm)
        if state:
            queue=self.queues[state]
            queue[:]=[item for item in queue if item is not vm]
        self.states[id(vm)]=0

    def request(self,vm,state):
        if not 0<=state<=4:raise ValueError('Unknown scheduler state')
        if self.priorities[state]<self.priorities[self.state(vm)]:return False
        self.remove(vm)
        self.states[id(vm)]=state
        if state:self.queues[state].insert(0,vm)
        return True

    def raise_state(self,vm,state):
        # 416900 rejects equal priority and inserts before the circular head
        # without changing that head: FIFO tail insertion. 416A40 instead
        # accepts equality and updates the head (LIFO insertion).
        if not 0<=state<=4:raise ValueError('Unknown scheduler state')
        if self.priorities[state]<=self.priorities[self.state(vm)]:return False
        self.remove(vm)
        self.states[id(vm)]=state
        if state:self.queues[state].append(vm)
        return True

    def wake_waiting(self):
        return self.promote(4)

    def promote(self,source):
        if source not in (2,3,4):raise ValueError('Unknown promotion source')
        if any(self.queues[state] for state in range(1,source)):return -1
        self.queues[1]=self.queues[source]
        self.queues[source]=[]
        for vm in self.queues[1]:self.states[id(vm)]=1
        return -1 if self.queues[1] else 1

    def run_one(self):
        if not self.queues[1]:return None
        vm=self.queues[1][0]
        self.remove(vm)
        result=vm.run()
        if result['reason']=='yield' and result.get('state') is not None:
            # The original VM's yield handlers call 416900, not 416A40.
            # Preserve execution order and any higher/equal priority wakeup
            # performed while the VM was running.
            self.raise_state(vm,result['state'])
        return vm,result
