"""Bounded readers for user-supplied Rich Diamond resource containers.

No game assets, executable patches or registration logic are included.
CCLS is deliberately an inspection format, not a certified gameplay import.
"""
import hashlib
import struct
import zlib
import binascii


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decompress_ca(data, limit=64 * 1024 * 1024):
    if data[:1] != b'\xca':
        raise ValueError('Expected CA stream')
    pos = 8
    nodes = leaves = ends = 0

    def bit():
        nonlocal pos
        if pos >= len(data) * 8:
            raise ValueError('Truncated CA bitstream')
        value = (data[pos // 8] >> (7 - pos % 8)) & 1
        pos += 1
        return value

    def tree(depth=0):
        nonlocal nodes, leaves, ends
        nodes += 1
        if depth > 256 or nodes > 1025:
            raise ValueError('CA tree exceeds bounds')
        if not bit():
            return tree(depth + 1), tree(depth + 1)
        leaves += 1
        if leaves > 257:
            raise ValueError('Too many CA leaves')
        if bit():
            ends += 1
            return None
        value = 0
        for _ in range(8):
            value = value * 2 + bit()
        return value

    root = tree()
    if ends != 1 or (not isinstance(root, tuple) and root is not None):
        raise ValueError('CA tree must have one EOF and make progress')
    out = bytearray()
    while True:
        node = root
        while isinstance(node, tuple):
            node = node[bit()]
        if node is None:
            return bytes(out)
        if len(out) >= limit:
            raise ValueError('CA output exceeds configured limit')
        out.append(node)


def map_rows(data, full=True):
    """Read row-RLE, requiring its terminator and bounded rows/widths."""
    rows, row, pos = [], [], 0
    while pos < len(data):
        value = data[pos]
        pos += 1
        if value == 1:
            if row or pos != len(data):
                raise ValueError('Invalid map end or trailing bytes')
            if full and len(rows) != 128:
                raise ValueError('ST1 map must store 128 rows')
            return rows
        if value == 2:
            rows.append(row)
            row = []
            if len(rows) > 128:
                raise ValueError('Too many map rows')
        elif 3 <= value <= 31:
            if pos >= len(data):
                raise ValueError('Truncated map run')
            row.extend([data[pos]] * value)
            pos += 1
        else:
            row.append(value)
        if len(row) > 128:
            raise ValueError('Map row wider than canvas')
    raise ValueError('Missing map terminator')


def st1(data):
    if data[:4] != b'ST1\n':
        raise ValueError('Expected ST1')
    pos = 4

    def take(size):
        nonlocal pos
        if size < 0 or pos + size > len(data):
            raise ValueError('Truncated ST1')
        value = data[pos:pos + size]
        pos += size
        return value

    def word():
        return int.from_bytes(take(2), 'little')

    flags = word()
    base = take(word()).decode('latin1')
    count = word()
    if not 1 <= count <= 400:
        raise ValueError('ST1 count out of bounds')
    levels = []
    for index in range(count):
        name = take(word()).decode('latin1')
        packed = take(word())
        trailer = take(14)
        rows = map_rows(packed)
        levels.append(dict(number=index + 1, name=name, rows=rows,
                           packed_sha256=digest(packed), trailer_hex=trailer.hex()))
    return dict(format='ST1', flags=flags, base=base, count=count, levels=levels,
                consumed=pos, footer_bytes=len(data) - pos,
                validation='strict row-RLE; raw tile codes, no behavior conversion')


def ccls_inspect(data):
    """Strict CCLS 2.0 records; retain unconverted metadata and footer."""
    if data[:8] != b'CCLS\x02\x00\x01\x01' or len(data) < 9:
        raise ValueError('Unsupported CCLS header/version')
    count, pos = data[8], 9
    if not 1 <= count <= 255:
        raise ValueError('Invalid CCLS count')

    def take(size):
        nonlocal pos
        if size < 0 or pos + size > len(data):
            raise ValueError('Truncated CCLS')
        value = data[pos:pos + size]
        pos += size
        return value

    def word():
        return int.from_bytes(take(2), 'little')

    levels = []
    for index in range(count):
        begin = pos
        name = take(word()).decode('latin1')
        packed = take(word())
        rows = map_rows(packed, full=False)
        meta_start = pos
        fixed = take(9)
        commands = []
        while True:
            offset = pos
            command = take(1)[0]
            if command == 0:
                break
            if command != 4:
                raise ValueError(f'Unsupported CCLS level command {command} at {offset:#x}')
            size = take(1)[0]
            pairs = [list(take(2)) for _ in range(size)]
            commands.append(dict(opcode=command, offset=offset, pairs_raw=pairs))
        if len(commands)>1:
            raise ValueError('Multiple CCLS tile tables need native validation')
        pairs = commands[0]['pairs_raw'] if commands else []
        variants=[]
        for selection in (0,1):
            variant=[]
            for row in rows:
                variant.append([pairs[tile-(256-len(pairs))][selection]
                                if pairs and tile>=256-len(pairs) else tile for tile in row])
            variants.append(dict(table=selection,rows=variant))
        levels.append(dict(number=index + 1, name=name, rows=rows,
                           stored_rows=len(rows), row_lengths=list(map(len, rows)),
                           packed_sha256=digest(packed), offset=begin, next_offset=pos,
                           metadata_hex=data[meta_start:pos].hex(),
                           metadata_fields_raw=[int.from_bytes(fixed[:2], 'little'),
                                                *fixed[2:5], int.from_bytes(fixed[5:], 'little')],
                           commands=commands,variants=variants,
                           variant_policy='native high-tile lookup; table selection retained explicitly, no default branch inferred'))
    return dict(format='CCLS', count=count, header_hex=data[:9].hex(), levels=levels,
                consumed=pos, footer_bytes=len(data) - pos, footer_hex=data[pos:].hex(),
                validation='strict supported record grammar; metadata commands/footer retained; gameplay semantics not certified')


def inspect_payload(data):
    result = dict(wrapper='raw', input_bytes=len(data), input_sha256=digest(data))
    plain = decompress_ca(data) if data[:1] == b'\xca' else data
    if data[:1] == b'\xca':
        result['wrapper'] = 'CA'
    result.update(plain_bytes=len(plain), plain_sha256=digest(plain), head=plain[:16].hex())
    if plain[:4] == b'ST1\n':
        result['levelset'] = st1(plain)
    elif plain[:4] == b'CCLS':
        result['levelset'] = ccls_inspect(plain)
    elif plain[:4] == b'LV2\n':
        result.update(format='LV2', validation='preserved text; not converted to game state')
    elif plain[:2] in (b'\xcb\xfe', b'\xcb\xfc'):
        result.update(format='CB resource wrapper', validation='decoder pending; preserved byte-for-byte')
    elif plain[:1] == b'\xcb':
        result.update(format='unknown CB variant', validation='unsupported; preserved byte-for-byte')
    elif plain[:4] == b'MThd':
        result['format'] = 'MIDI'
    elif plain[:4] == b'RIFF' and plain[8:12] in (b'WAVE', b'AVI '):
        result['format'] = plain[8:12].decode('ascii').strip()
    elif len(plain) >= 128 and plain[:1] == b'\x0a':
        x0, y0, x1, y1 = struct.unpack_from('<4H', plain, 4)
        result.update(format='PCX header candidate', width=x1 - x0 + 1, height=y1 - y0 + 1)
    else:
        result['format'] = 'unclassified'
    if plain[:6] in (b'CCIg11', b'CCIg12', b'CCIb10'):
        result['format'] = plain[:6].decode('ascii')
    return plain, result


def pcx_png(data):
    """Decode 8-bit one-plane PCX to indexed PNG, without inventing transparency."""
    if len(data) < 897 or data[:4] != b'\x0a\x05\x01\x08' or data[65] != 1 or data[-769] != 12:
        raise ValueError('Unsupported PCX layout/palette')
    x0, y0, x1, y1 = struct.unpack_from('<4H', data, 4)
    width, height = x1 - x0 + 1, y1 - y0 + 1
    stride = struct.unpack_from('<H', data, 66)[0]
    if not (1 <= width <= stride <= 4096 and 1 <= height <= 4096):
        raise ValueError('PCX dimensions out of bounds')
    end, pos, pixels = len(data) - 769, 128, bytearray()
    while pos < end:
        value = data[pos]; pos += 1
        count = 1
        if value >= 192:
            count = value & 63
            if count == 0 or pos >= end:
                raise ValueError('Invalid PCX RLE')
            value = data[pos]; pos += 1
        pixels.extend(bytes([value]) * count)
        if len(pixels) > stride * height + 1:
            raise ValueError('PCX pixel overflow')
    if len(pixels) < stride * height:
        raise ValueError('Truncated PCX pixels')
    extra = bytes(pixels[stride * height:])
    rows = b''.join(b'\0' + bytes(pixels[y * stride:y * stride + width]) for y in range(height))
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', binascii.crc32(kind + payload) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>2I5B', width, height, 8, 3, 0, 0, 0))
    png += chunk(b'PLTE', data[-768:])
    png += chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')
    return png, dict(width=width, height=height, stride=stride, extra_hex=extra.hex(),
                     indexed_pixels_sha256=digest(b''.join(bytes(pixels[y * stride:y * stride + width]) for y in range(height))),
                     transparency='none; sprite masks require engine metadata')
