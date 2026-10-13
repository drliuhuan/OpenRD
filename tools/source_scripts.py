"""Strict BYT structural readers; script parsing does not certify VM semantics."""
import struct
from source_formats import digest


class Reader:
    def __init__(self, data, pos=0, mode='inline'):
        self.data, self.pos, self.mode = data, pos, mode

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError('Truncated BYT record')
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    def byte(self):
        return self.take(1)[0]

    def words(self, count):
        return list(struct.unpack('<' + 'H' * count, self.take(count * 2)))

    def string(self):
        if self.mode == 'reference24':
            key = list(self.take(3))
            return dict(string_ref=int.from_bytes(bytes(key), 'big'), string_key=key)
        ref, size = self.words(2)
        return dict(string_ref=ref, text=self.take(size).decode('latin1'))


def byt(data, mode, embedded=False):
    if data[:6] != b'CCIb10' or mode not in ('inline', 'reference24'):
        raise ValueError('Unknown BYT format/mode')
    r = Reader(data, 6, mode)
    records = []
    while r.pos < len(data):
        begin = r.pos
        op = r.byte()
        record = dict(offset=begin, opcode=op)
        if op == 0:
            record['next_offset'] = r.pos
            records.append(record)
            tail = r.take(len(data) - r.pos)
            if not embedded and tail.strip(b'\0'):
                raise ValueError('Nonzero bytes after BYT terminator')
            return dict(format='CCIb10', string_mode=mode, records=records,
                        decoded_sha256=digest(data), decoded_bytes=len(data),
                        stop_offset=record['next_offset'], padding_bytes=0 if embedded else len(tail),
                        complete=True, terminated=True, record_count=len(records),
                        object_count=sum(x['opcode'] == 1 for x in records),
                        validation='strict stream structure; VM behavior not certified')
        if op == 1:
            first, second, word, byte, flags, w1, w2, graphic, last = struct.unpack('<BBHBBHHHB', r.take(13))
            record.update(leading_bytes_raw=[first, second], tile_code=first,
                          resource_id=graphic, parameter_raw=word, byte_raw=byte,
                          flags_raw=flags, words_raw=[w1, w2], graphic_id_raw=graphic,
                          last_byte_raw=last, commands=[])
            while True:
                offset = r.pos
                sub = r.byte()
                if sub == 1:
                    break
                command = dict(offset=offset, subcommand=sub)
                if sub == 2:
                    command.update(leading_words_raw=r.words(2), bytes_raw=list(r.take(2)), trailing_words_raw=r.words(2))
                elif sub == 3:
                    command['value_raw'] = r.byte()
                elif sub == 4:
                    command['value_raw'] = r.words(1)[0]
                elif sub in (5, 7):
                    command.update(r.string())
                elif sub == 6:
                    command['bytes_raw'] = list(r.take(3))
                else:
                    raise ValueError(f'Unsupported BYT object command {sub} at {offset:#x}')
                command['next_offset'] = r.pos
                record['commands'].append(command)
        elif op == 2:
            flag, values = r.byte(), r.words(6)
            record.update(byte_raw=flag, words_raw=values, payload_hex=r.take(values[2]).hex())
        elif op in (3, 4, 5, 6, 7, 8):
            record['bytes_raw'] = list(r.take(4 if op == 7 else 1))
        else:
            raise ValueError(f'Unsupported BYT opcode {op} at {begin:#x}')
        record['next_offset'] = r.pos
        records.append(record)
        if len(records) > 65536:
            raise ValueError('BYT record count exceeds bounds')
    raise ValueError('Missing BYT terminator')


def identify_byt(data):
    candidates = []
    failures = []
    for mode in ('inline', 'reference24'):
        try:
            candidates.append(byt(data, mode))
        except ValueError as exc:
            failures.append(str(exc))
    if len(candidates) != 1:
        raise ValueError('BYT mode ambiguous or unsupported: ' + '; '.join(failures))
    return candidates[0]


def gin(data):
    from gin_prefix import parse as prefix
    from gin_sprite_island import parse as island
    first=prefix(data)
    tail=island(data,first['stop_offset'],bitmap=None,width=4096,height=4096)
    records=first['records']+tail['records']
    if data[:6] == b'CCIg12':
        from source_pixels import inspect
        for record in records:
            if record['opcode'] == 35:
                record['shade_slot'] = record['flags_raw'][2]
                record['pixels'] = inspect(bytes.fromhex(record['encoded_pixels_hex']),
                                           *record['dimensions'])
    return dict(format=data[:6].decode('ascii'),decoded_sha256=digest(data),decoded_bytes=len(data),
                records=records,record_count=len(records),stop_offset=tail['stop_offset'],
                stop_opcode=tail['stop_opcode'],stop_reason=tail['stop_reason'],
                complete=tail['terminated'] and tail['trailing_bytes']==0,
                sprite_count=tail['sprite_count'],object_count=tail['object_count'],
                validation='structural reader; modern UI tail/rendering semantics may be incomplete')
