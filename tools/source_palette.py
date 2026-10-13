"""Indexed effect-table registration; RGB palette construction is separate.

408810 maps an effect table through enabled palette indices and deduplicates
the resulting 256 bytes. Unwritten indices retain the shared scratch buffer.
467D50 resolves the sprite's shade slot.
"""
IDENTITY = bytes(range(256))


class EffectRegistry:
    def __init__(self, palette_remap=IDENTITY, enabled=False, scratch=None):
        palette_remap = bytes(palette_remap)
        if len(palette_remap) != 256:
            raise ValueError('Palette remap must contain 256 indices')
        if scratch is None:
            scratch = bytearray(256)
        if not isinstance(scratch, bytearray) or len(scratch) != 256:
            raise ValueError('Scratch must be a shared 256-byte bytearray')
        self.palette_remap = palette_remap
        self.enabled = bool(enabled)
        self.scratch = scratch
        self.tables = []

    def prepare(self, table):
        if len(self.scratch) != 256:
            raise ValueError('Shared scratch must remain 256 bytes')
        table = bytes(table)
        if len(table) != 256:
            raise ValueError('Effect table must contain 256 indices')
        if not self.enabled or self.palette_remap == IDENTITY:
            return table
        output = bytearray(self.scratch)
        for i, value in enumerate(table):
            output[self.palette_remap[i]] = self.palette_remap[value]
        return bytes(output)

    def register(self, table):
        prepared = self.prepare(table)
        if self.enabled and self.palette_remap != IDENTITY:
            # Actual 47C308 is shared across registry objects. Commit even when
            # deduplication subsequently returns an existing slot.
            self.scratch[:] = prepared
        try:
            return self.tables.index(prepared)
        except ValueError:
            if len(self.tables) >= 32767:
                raise ValueError('Native signed effect slot limit exceeded')
            self.tables.append(prepared)
            return len(self.tables) - 1

    def resolve(self, slot):
        if type(slot) is not int:
            raise ValueError('Integer effect slot required')
        return self.tables[slot] if 0 <= slot < len(self.tables) else IDENTITY

    def sprite_shade(self, sprite):
        # Actual opcode35 writes flags_raw[2] to the 16-byte sprite's +0xC.
        flags = sprite['flags_raw']
        if len(flags) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in flags):
            raise ValueError('Expected CCIg12 sprite flags')
        return self.resolve(flags[2])

    def draw_sprite(self, sprite, destination, surface_width, surface_height,
                    position, clip, fill, remap=None, bottom_up=False):
        from source_pixels import draw_surface
        if sprite.get('opcode') != 35 or len(sprite['origin_raw']) != 2:
            raise ValueError('Expected indexed CCIg12 sprite')
        origin = tuple(v - 65536 if v >= 32768 else v for v in sprite['origin_raw'])
        return draw_surface(bytes.fromhex(sprite['encoded_pixels_hex']),
                            *sprite['dimensions'], destination, surface_width,
                            surface_height, position, origin, clip, fill,
                            self.sprite_shade(sprite), remap, bottom_up)
