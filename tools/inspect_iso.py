"""Read ISO9660 little-endian directory fields; never modify the image.

This image has inconsistent big-endian mirrors. Report them instead of
silently treating extraction success as proof of a healthy filesystem.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

def inspect(path):
    data = Path(path).read_bytes()
    mismatches = []
    def both(buf, pos, label):
        little = struct.unpack_from('<I', buf, pos)[0]
        big = struct.unpack_from('>I', buf, pos + 4)[0]
        if little != big:
            mismatches.append({'field': label, 'little': little, 'big': big})
        return little
    pvd = data[16 * 2048:17 * 2048]
    if pvd[:7] != b'\x01CD001\x01':
        raise ValueError('Primary volume descriptor not found at sector 16')
    volume_sectors = both(pvd, 80, 'pvd:volume_space_size')
    if volume_sectors * 2048 > len(data):
        raise ValueError('Declared volume exceeds image')
    files = []
    def walk(record, prefix):
        extent = both(record, 2, prefix + ':extent')
        size = both(record, 10, prefix + ':size')
        start = extent * 2048
        if start + size > len(data):
            raise ValueError('Extent outside image: ' + prefix)
        block = data[start:start + size]
        pos = 0
        while pos < len(block):
            length = block[pos]
            if not length:
                pos = (pos // 2048 + 1) * 2048
                continue
            row = block[pos:pos + length]
            if length < 34 or len(row) != length:
                raise ValueError('Malformed directory record')
            name = row[33:33 + row[32]]
            pos += length
            if name in (b'\x00', b'\x01'):
                continue
            name = name.decode('ascii').split(';')[0]
            full = prefix + name
            if row[25] & 2:
                walk(row, full + '/')
            else:
                offset = both(row, 2, full + ':extent') * 2048
                count = both(row, 10, full + ':size')
                if offset + count > len(data):
                    raise ValueError('File outside image: ' + full)
                payload = data[offset:offset + count]
                entry = {'path': full, 'offset': offset, 'size': count,
                         'sha256': hashlib.sha256(payload).hexdigest()}
                if full.lower().endswith(('.gin', '.byt', '.lvs', '.dat')):
                    entry['head_hex'] = payload[:32].hex(' ')
                if full.lower().endswith('.gin'):
                    entry['references'] = []
                    for needle in (b'RichDimd.dat', b'title.pcx', b'CCIg11'):
                        at = payload.find(needle)
                        entry['references'].append({'text': needle.decode(), 'offset': at,
                            'context_hex': payload[max(0, at-16):at+len(needle)+16].hex(' ') if at >= 0 else None})
                files.append(entry)
    walk(pvd[156:190], '')
    return {'image': str(Path(path).resolve()), 'size': len(data),
            'sha256': hashlib.sha256(data).hexdigest(),
            'endianness_mismatches': mismatches, 'files': files}

