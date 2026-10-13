"""Fixed-key CB FE resource stream decoder, using tables from a local engine.

The engine is read as a PE file and never executed. No tables or game data are
bundled. Other CB variants and registration-dependent streams are unsupported.
"""
from pathlib import Path
import struct


def engine_tables(path):
    if Path(path).stat().st_size > 128 * 1024 * 1024:
        raise ValueError('Oversized PE engine')
    raw = Path(path).read_bytes()
    if raw[:2] != b'MZ' or len(raw) < 64:
        raise ValueError('Invalid or oversized PE engine')
    pe = struct.unpack_from('<I', raw, 60)[0]
    if pe + 84 > len(raw) or raw[pe:pe + 4] != b'PE\0\0':
        raise ValueError('Invalid PE header')
    opt = struct.unpack_from('<H', raw, pe + 20)[0]
    if struct.unpack_from('<H', raw, pe + 24)[0] != 0x10b:
        raise ValueError('Only PE32 engines supported')
    base = struct.unpack_from('<I', raw, pe + 52)[0]
    count = struct.unpack_from('<H', raw, pe + 6)[0]
    if count > 96 or pe + 24 + opt + count * 40 > len(raw):
        raise ValueError('Invalid PE section table')
    sections = []
    for i in range(count):
        _, rva, size, off = struct.unpack_from('<4I', raw, pe + 24 + opt + 40 * i + 8)
        if off + size > len(raw):
            raise ValueError('Truncated PE section')
        sections.append((rva, size, off))

    def table(address):
        rva = address - base
        for start, size, off in sections:
            if start <= rva and rva + 1026 <= start + size:
                return struct.unpack_from('<513H', raw, off + rva - start)
        raise ValueError('Table outside PE sections')

    def validate(left, right):
        seen, symbols = set(), set()
        def walk(node, depth):
            if node >= 513 or node in seen or depth > 24:
                raise ValueError('Invalid CB tree')
            seen.add(node)
            if left[node]:
                walk(left[node], depth + 1)
                walk(right[node], depth + 1)
            else:
                value = right[node]
                symbol = 256 if value == 0xffff else value & 255
                if value != 0xffff and value >> 8 != depth:
                    raise ValueError('CB code length mismatch')
                if symbol in symbols:
                    raise ValueError('Repeated CB symbol')
                symbols.add(symbol)
        walk(0, 0)
        if len(seen) != 513 or symbols != set(range(257)):
            raise ValueError('Incomplete CB tree')

    candidates = []
    for offset in range(len(raw) - 22):
        # Two adjacent mov eax, table-address / ret accessors, 16 bytes apart.
        if raw[offset] == 0xb8 and raw[offset + 5] == 0xc3 and raw[offset + 16] == 0xb8 and raw[offset + 21] == 0xc3:
            a = struct.unpack_from('<I', raw, offset + 1)[0]
            b = struct.unpack_from('<I', raw, offset + 17)[0]
            if b - a != 1032:
                continue
            try:
                left, right = table(a), table(b)
                validate(left, right)
                candidates.append((left, right, dict(accessor_file_offset=offset, left_address=a, right_address=b)))
            except (ValueError, struct.error):
                continue
    if len(candidates) != 1:
        raise ValueError(f'Expected one validated CB tree, found {len(candidates)}')
    return candidates[0]


def decode_cb(data, tables, limit=64 * 1024 * 1024):
    if data[:2] != b'\xcb\xfe':
        raise ValueError('Only fixed-key CB FE is supported')
    left, right = tables[:2]
    state = 0x436f7265
    def random(bits):
        nonlocal state
        for _ in range(bits):
            feedback = ((state >> 1) ^ (state >> 5) ^ (state >> 6) ^ (state >> 31)) & 1
            state = (state >> 1) | (feedback << 31)
        return state & ((1 << bits) - 1)
    perm = list(range(256)); freq = [0] * 256
    total = 0
    for index in range(255, -1, -1):
        total += random(3)
        freq[index] = total
    for index in range(256):
        other = random(8)
        perm[index], perm[other] = perm[other], perm[index]
    pos = 16
    out = bytearray()
    while True:
        node = 0
        while left[node]:
            if pos >= len(data) * 8:
                raise ValueError('Truncated CB bitstream')
            bit = (data[pos // 8] >> (7 - pos % 8)) & 1
            pos += 1
            node = right[node] if bit else left[node]
        value = right[node]
        if value == 0xffff:
            return bytes(out)
        index = value & 255
        if len(out) >= limit:
            raise ValueError('CB output exceeds configured limit')
        out.append(perm[index])
        freq[index] += 1
        if freq[index] > 32000:
            freq = [f >> 4 for f in freq]
        if index and freq[index] > freq[index - 1]:
            perm[index], perm[index - 1] = perm[index - 1], perm[index]
            freq[index], freq[index - 1] = freq[index - 1], freq[index]
