"""Parse GIN sequentially from its header up to the first unsupported command."""
import argparse
import json
from pathlib import Path
import rdtool
import gin_prefix
import gin_sprite_island

def parse(data):
    prefix=gin_prefix.parse(data)
    if prefix['stop_opcode']!=0x23:
        return prefix
    tail=gin_sprite_island.parse(data,prefix['stop_offset'])
    records=prefix['records']+tail['records']
    if not all(a['next_offset']==b['offset'] for a,b in zip(records,records[1:])):
        raise ValueError('Noncontiguous stream')
    complete=tail['terminated'] and tail['trailing_bytes']==0
    tail.update(scope='complete sequential CCIg11 disc sample' if complete else 'sequential from CCIg11; incomplete or trailing data',
                complete=complete,
                start_offset=6,prefix_record_count=len(prefix['records']),
                record_count=len(records),records=records,
                parsed_bytes=tail['stop_offset']-6,decoded_bytes=len(data))
    return tail

