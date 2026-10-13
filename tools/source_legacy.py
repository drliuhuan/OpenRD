"""Recover 1999 built-in maps from a local PE, without bundled map data."""
import re
import struct
from source_formats import digest, map_rows


def embedded_1999(raw):
    if raw[:2] != b'MZ' or len(raw) < 64:
        return []
    pe = struct.unpack_from('<I', raw, 60)[0]
    if pe + 84 > len(raw) or raw[pe:pe + 4] != b'PE\0\0':
        raise ValueError('Invalid PE')
    count, opt = struct.unpack_from('<H', raw, pe + 6)[0], struct.unpack_from('<H', raw, pe + 20)[0]
    if count > 96 or pe + 24 + opt + count * 40 > len(raw):
        raise ValueError('Invalid PE sections')
    base = struct.unpack_from('<I', raw, pe + 52)[0]
    sections = []
    for n in range(count):
        h = pe + 24 + opt + 40 * n
        _, rva, size, off = struct.unpack_from('<4I', raw, h + 8)
        flags = struct.unpack_from('<I', raw, h + 36)[0]
        if off + size > len(raw):
            raise ValueError('Truncated PE section')
        sections.append((base + rva, size, off, flags))

    def read(va, size):
        for start, length, off, _ in sections:
            if start <= va and va + size <= start + length:
                return raw[off + va - start:off + va - start + size]
        raise ValueError('Map pointer outside PE')

    # Exact original function except its relative allocation call displacement.
    prefix = bytes.fromhex('535556578b7c24188d470150e8')
    suffix = bytes.fromhex('8be883c40433db33c085ffb2637e2a8b4c24148bf52bf1897c2414321188140e8a11885424188b44241825ff00000003d8414f75e68b442414c60428008b44241c3bd8740cc6450020c6450102c64502015f8bc55e5d5bc3')
    functions = []
    for start, length, off, flags in sections:
        if not flags & 0x20000000:
            continue
        code = raw[off:off + length]
        for match in re.finditer(re.escape(prefix) + b'.{4}' + re.escape(suffix), code, re.DOTALL):
            functions.append(start + match.start())
    if not functions:
        return []
    levels = []
    for start, length, off, flags in sections:
        if not flags & 0x20000000:
            continue
        code = raw[off:off + length]
        for match in re.finditer(b'\x68(.{4})\x68(.{4})\x68(.{4})\xe8(.{4})', code, re.DOTALL):
            checksum, size, pointer = (struct.unpack('<I', match.group(n))[0] for n in (1, 2, 3))
            call = start + match.start() + 15
            target = call + 5 + struct.unpack('<i', match.group(4))[0]
            if target not in functions:
                continue
            if not 3 <= size <= 32768:
                raise ValueError('Embedded map size out of bounds')
            packed = read(pointer, size)
            if sum(packed) != checksum:
                raise ValueError('Embedded map checksum mismatch')
            previous = 0x63
            plain = bytearray()
            for value in packed:
                plain.append(previous ^ value)
                previous = value
            rows = map_rows(plain, full=False)
            name = None
            # Constructor duplicates the preceding constant string into name.
            for i in range(max(0, match.start() - 160), match.start() - 9):
                if code[i] != 0x68:
                    continue
                address = struct.unpack_from('<I', code, i + 1)[0]
                try:
                    text = bytearray()
                    for n in range(80):
                        value = read(address + n, 1)[0]
                        if value == 0:
                            break
                        text.append(value)
                    else:
                        continue
                except ValueError:
                    continue
                if text and all(32 <= b < 127 for b in text):
                    name = text.decode('ascii')
            levels.append(dict(number=len(levels) + 1, name=name, rows=rows,
                               constructor_call=call, decoder_address=target,
                               source_address=pointer, source_bytes=size, checksum=checksum,
                               packed_sha256=digest(packed), decoded_sha256=digest(plain),
                               validation='original decoder signature, checksum and strict row-RLE'))
    return levels
