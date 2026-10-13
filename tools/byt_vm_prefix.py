"""Conservative linear instruction prefixes, never resynchronize on unknown bytes.

This is neither a control-flow decoder nor a VM emulator. A resource setter
may consume values computed earlier; opcode 51 has no immediate resource ID.
"""
import json
from pathlib import Path

# Operand widths verified in CCENG 0x41755F's opcode dispatcher.
WIDTHS = {0:0, 1:1, 2:2, 3:0, 6:0, 7:0, 8:0, 9:0, 35:0, 36:2, 66:2, 67:0, 68:1, 69:0, 92:1, 94:1, 139:0, 140:0, 141:0, 142:0,
          57:0, 58:0, 59:0, 79:0, 86:0, 88:0, 91:0, 93:0, 98:0, 99:0, 104:0, 106:0, 115:0, 120:0, 143:0,
          **{i:0 for i in range(10,23)}, 23:1, 51:0, 75:0,
          30:3, 32:1, 38:1, 39:0, 44:2, 46:2, 64:1, 72:2, 74:2, 89:0, 90:0,
          27:0, 28:0, 48:2, 50:2, 55:2, 61:0, 63:0, 65:0, 76:0, 77:0, 78:0, 95:0, 96:0, 97:0, 100:0, 101:1, 102:0, 103:1, 105:1, 107:1, 114:0, 124:2, 125:2, 126:2,
          127:2, 128:0, 129:0, 130:0, 131:0, 133:0, 136:0, 138:2, 144:3, 145:3, 146:3, 147:3}

def prefix(data):
    pos = 0
    instructions = []
    while pos < len(data):
        opcode = data[pos]
        if opcode not in WIDTHS:
            return dict(instructions=instructions, stop_offset=pos,
                        stop_opcode=opcode, stop_reason='unresearched opcode width', complete=False)
        end = pos + 1 + WIDTHS[opcode]
        if end > len(data):
            return dict(instructions=instructions, stop_offset=pos,
                        stop_opcode=opcode, stop_reason='truncated operand', complete=False)
        item = dict(offset=pos, opcode=opcode, operand_hex=data[pos+1:end].hex(), next_offset=end)
        if opcode in (144,145,146,147):
            item.update(comparison_value=data[pos+1], jump_when='equal' if opcode in (145,147) else 'not_equal',
                        stack_access='pop' if opcode in (146,147) else 'last_value_register',
                        jump_target=int.from_bytes(data[pos+2:end], 'little', signed=True))
        if opcode in (124,125,126,127):
            item.update(jump_target=int.from_bytes(data[pos+1:end], 'little', signed=True),
                        jump_when={124:'nonzero',125:'zero',126:'always',127:'call'}[opcode])
        instructions.append(item)
        pos = end
    return dict(instructions=instructions, stop_offset=pos, stop_opcode=None,
                stop_reason=None, complete=True)

def report(root):
    byt = json.loads((root/'evidence/byt-complete-index.json').read_text())
    gin = json.loads((root/'evidence/gin-complete-index.json').read_text())
    resources = {r['resource_id'] for r in gin['records'] if r['opcode']==36}
    blocks = []
    truncation_checks = 0
    for record in byt['records']:
        if record['opcode'] != 2:
            continue
        data = bytes.fromhex(record['payload_hex'])
        decoded = prefix(data)
        for instruction in decoded['instructions']:
            for end in range(instruction['offset']+1, instruction['next_offset']):
                assert prefix(data[:end])['stop_reason'] == 'truncated operand'
                truncation_checks += 1
        boundaries = {i['offset'] for i in decoded['instructions']}
        for instruction in decoded['instructions']:
            if 'jump_target' in instruction:
                target = instruction['jump_target']
                instruction['target_in_payload'] = 0 <= target < len(data)
                instruction['target_boundary_status'] = ('confirmed' if target in boundaries else
                    'operand_byte' if 0 <= target < decoded['stop_offset'] else 'not_decoded')
                assert instruction['target_in_payload']
                assert instruction['target_boundary_status'] != 'operand_byte'
        sites = []
        instructions = decoded['instructions']
        for n, instruction in enumerate(instructions):
            if instruction['opcode'] != 51:
                continue
            site = dict(offset=instruction['offset'], resource_id=None,
                        scope='Local literal operands only; execution reachability unproven')
            if n >= 2 and instructions[n-2]['opcode']==23 and instructions[n-1]['opcode'] in (1,2):
                pair = int(instructions[n-2]['operand_hex'],16)
                x,y = (pair >> 4)&7, pair&7
                site['relative_xy'] = [-x if pair&128 else x, -y if pair&8 else y]
                site['resource_id'] = int.from_bytes(bytes.fromhex(instructions[n-1]['operand_hex']), 'little')
                site['gin_resource_resolves'] = site['resource_id'] in resources
                assert site['gin_resource_resolves']
                # A branch entering at the setter can supply different stack operands.
                site['external_entry_targets'] = [i['offset'] for i in instructions
                    if i.get('jump_target') in (instructions[n-1]['offset'], instruction['offset'])]
            sites.append(site)
        blocks.append(dict(byt_offset=record['offset'], program_id=record['byte_raw'], payload_bytes=len(data),
                           resource_setter_sites=sites, **decoded))
    return dict(scope='Linear prefixes only; no control-flow reachability or stack evaluation',
                known_opcode_width_count=len(WIDTHS), decoded_bytes=sum(b['stop_offset'] for b in blocks),
                complete_linear_blocks=sum(b['complete'] for b in blocks),
                truncation_checks=truncation_checks,
                setter_site_count=sum(len(b['resource_setter_sites']) for b in blocks), blocks=blocks)

