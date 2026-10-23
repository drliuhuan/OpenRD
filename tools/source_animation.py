"""Source GIN timelines with theme IMC motion nodes; no ISO frame remapping."""
from copy import deepcopy
from gin_graphics_state import Archetype, Instance


def expand_motion(gin, renderer, theme=''):
    """Lower GIN macro nodes to their own IMC offsets/resources and return node.

    This preserves every source node. It never interpolates positions or
    normalizes the length to a different version's animation.
    """
    records=[]
    banks=renderer.themes.get(theme,{}).get('animations',{})
    for original in gin['records']:
        if original['opcode']==38 and original.get('subtype')!=4:continue
        if original['opcode']!=37:
            records.append(original);continue
        record=deepcopy(original)
        record['commands']=[c for c in record['commands'] if c['subcommand']!=4]
        for macro in (c for c in original['commands'] if c['subcommand']==4):
            group,selector,start,end=macro['values_raw']
            chain=banks.get((group,selector))
            if not chain:
                # GIN default graphics has its own short, static fallback.
                continue
            ids=[start]+list(range(len(record['entries_raw']),len(record['entries_raw'])+len(chain)-1))
            record['commands']=[c for c in record['commands'] if not(c['subcommand']==1 and c['values_raw'][0]==start)]
            for i,node in enumerate(chain):
                entry=[*node['offset_raw'],node['resource']]
                if i==0:record['entries_raw'][start]=entry
                else:record['entries_raw'].append(entry)
                record['commands'].append(dict(subcommand=1,values_raw=[ids[i],ids[i+1] if i+1<len(ids) else end]))
        records.append(record)
    return dict(gin,records=records)


def animation_catalog(gin):
    result=[]
    for r in gin['records']:
        if r['opcode']==37:
            result.append(dict(object=r['object_id'],actions=sorted({c['values_raw'][1] for c in r['commands'] if c['subcommand']==2})))
    return result


def action_frames(gin, object_id, action, limit=4096, wait=None):
    """Play one declared action from its declared wait, for asset inspection."""
    record=next((r for r in gin['records'] if r['opcode']==37 and r['object_id']==object_id),None)
    if record is None:raise ValueError('Unknown source animation object')
    command=next((c for c in record['commands'] if c['subcommand']==2 and c['values_raw'][1]==action
                  and (wait is None or c['values_raw'][0]==wait)),None)
    if command is None:raise ValueError('Unknown source animation action')
    instance=Instance(Archetype(record),cursor=command['values_raw'][0],action=action)
    frames=[]
    for _ in range(limit):
        status=instance.advance(1,choose=lambda count:0)
        frames.append(dict(resource=instance.resource,pixel=list(instance.position),cursor=instance.cursor))
        if status['stopped']:return frames
    raise ValueError('Source animation exceeded node budget')
