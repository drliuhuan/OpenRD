"""Expand researched GIN resource trees without guessing state selection."""
import argparse
import json
from pathlib import Path

def expand(resource_id, resources, sprites, ancestors=()):
    if resource_id in ancestors:raise ValueError(f'Resource cycle: {ancestors + (resource_id,)}')
    record=resources[resource_id];path=ancestors+(resource_id,)
    if record['subtype']==1:
        return dict(resource_id=resource_id,subtype=1,frames=[dict(
            sprite_id=f['sprite_id'],offset_raw=f['offset_raw'],
            sprite=sprites[f['sprite_id']]) for f in record['frames']])
    if record['subtype'] not in (2,3,4,5,6,7,8):
        raise ValueError(f'Unknown resource subtype {record["subtype"]}')
    result=dict(resource_id=resource_id,subtype=record['subtype'],
                parameters_raw=record.get('parameters_raw',[]),
                branches=[expand(i,resources,sprites,path) for i in record.get('resource_references',[])])
    if 'base_resource_id' in record:
        result['base']=expand(record['base_resource_id'],resources,sprites,path)
    if record['subtype']==6:
        result['parameters_raw']=record['parameters_raw']
    if 'sprite_reference' in record:
        result['sprite_reference']=sprites[record['sprite_reference']]
    return result

def first_frames(tree):
    """Preview policy only: select branch zero, preserving frame order."""
    if tree['subtype']==1:return tree['frames']
    if tree['subtype']==6:return first_frames(phase_resource(tree,0,0))
    if tree['subtype'] not in (3,4,5):
        raise ValueError(f'Preview selection unsupported for subtype {tree["subtype"]}')
    if not tree['branches']:return []
    return first_frames(tree['branches'][0])

def signed16(value):
    value &= 65535
    return value-65536 if value>=32768 else value

def cdiv(a,b):
    if b==0:raise ValueError('Zero native selector divisor')
    return (abs(a)//abs(b))*(-1 if (a<0)!=(b<0) else 1)

def phase_resource(tree,index,time):
    """0x42CE41: native subtype-6 phase window, explicit runtime inputs."""
    if tree['subtype']!=6:raise ValueError('Expected subtype 6')
    period,start,interval,_=map(signed16,tree['parameters_raw'])
    quotient=signed16(cdiv(signed16(index)+signed16(time),interval))
    phase=quotient-cdiv(quotient,period)*period
    if phase<0:phase+=period
    count=len(tree['branches'])
    return tree['branches'][phase-start] if start<=phase<start+count else tree['base']

def build(byt,gin):
    resources={r['resource_id']:r for r in gin['records'] if r['opcode']==36}
    sprites={r['sprite_id']:r for r in gin['records'] if r['opcode']==35}
    ids=sorted({r['resource_id'] for r in byt['records'] if r['opcode']==1 and r['resource_id']})
    return dict(scope='All branches preserved; no runtime selector or animation emulation',
                root_count=len(ids),resources=[expand(i,resources,sprites) for i in ids])

