"""Bounded ISO9660 reader for ISO2048 and raw2352 (+16/+24) source discs."""
import argparse
from pathlib import Path
from import_source import save, safe_name


class Disc:
    def __init__(self, path):
        self.path = Path(path)
        self.size = self.path.stat().st_size
        self.stride = self.header = None
        with self.path.open('rb') as stream:
            for stride, header in ((2048, 0), (2352, 16), (2352, 24)):
                if self.size % stride:
                    continue
                stream.seek(16 * stride + header)
                probe = stream.read(7)
                if probe == b'\x01CD001\x01':
                    self.stride, self.header = stride, header
                    break
        if self.stride is None:
            raise ValueError('Unsupported disc layout')
        self.logical_size = self.size // self.stride * 2048

    def read(self, offset, size):
        if offset < 0 or size < 0 or offset + size > self.logical_size:
            raise ValueError('Disc read out of bounds')
        chunks = []
        with self.path.open('rb') as stream:
            while size:
                sector, inner = divmod(offset, 2048)
                count = min(2048 - inner, size)
                stream.seek(sector * self.stride + self.header + inner)
                data = stream.read(count)
                if len(data) != count:
                    raise ValueError('Short disc read')
                chunks.append(data)
                offset += count; size -= count
        return b''.join(chunks)

    def entries(self):
        pvd = self.read(16 * 2048, 2048)
        root = pvd[156:190]
        seen = set()
        count = 0
        def walk(extent, length, prefix='', depth=0):
            nonlocal count
            if depth > 32 or length > 16 * 1024 * 1024 or (extent, length) in seen:
                raise ValueError('Invalid/cyclic ISO directory')
            seen.add((extent, length))
            data = self.read(extent * 2048, length)
            pos = 0
            while pos < len(data):
                size = data[pos]
                if size == 0:
                    pos = (pos // 2048 + 1) * 2048
                    continue
                record = data[pos:pos + size]; pos += size
                if len(record) != size or size < 34 or 33 + record[32] > size:
                    raise ValueError('Malformed ISO directory record')
                name = record[33:33 + record[32]]
                if name in (b'\x00', b'\x01'):
                    continue
                name = name.decode('ascii', 'strict').split(';')[0]
                safe_name(name)
                ex = int.from_bytes(record[2:6], 'little')
                length = int.from_bytes(record[10:14], 'little')
                path = prefix + '/' + name if prefix else name
                directory = bool(record[25] & 2)
                count += 1
                if count > 100000:
                    raise ValueError('ISO entry count limit')
                yield path, ex * 2048, length, directory
                if directory:
                    yield from walk(ex, length, path, depth + 1)
        yield from walk(int.from_bytes(root[2:6], 'little'), int.from_bytes(root[10:14], 'little'))




