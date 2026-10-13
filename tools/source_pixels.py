"""Bounded CCIg12 scanline commands, independent of palette/window state.

The draw operation requires an indexed destination, a fill colour and a 256-byte
shade table. It deliberately does not turn background-dependent effects into PNG.
"""
import struct


def scanlines(data, width, height):
    if not 0 <= width <= 4096 or not 0 <= height <= 4096:
        raise ValueError('Invalid inline dimensions')
    if not width or not height:
        if data:
            raise ValueError('Pixels on empty inline sprite')
        return [[] for _ in range(height)]
    if len(data) < height * 2:
        raise ValueError('Truncated inline row table')
    result = []
    for offset in struct.unpack_from(f'<{height}H', data):
        if not offset:
            result.append([])
            continue
        if not height * 2 <= offset < len(data):
            raise ValueError('Inline row pointer outside payload')
        pos, x, commands = offset, 0, []
        while True:
            if pos >= len(data):
                raise ValueError('Missing inline row terminator')
            token = data[pos]
            pos += 1
            if not token:
                break
            count, kind = token & 63, token >> 6
            if not count:
                raise ValueError('Zero-length inline command')
            if x + count > width:
                raise ValueError('Inline row exceeds width')
            literal = b''
            if kind == 0:
                if pos + count > len(data):
                    raise ValueError('Truncated inline literal')
                literal = data[pos:pos + count]
                pos += count
            commands.append((x, count, kind, literal))
            x += count
        result.append(commands)
    return result


def draw(data, width, height, destination, fill, shade):
    if len(destination) != width * height or not 0 <= fill <= 255 or len(shade) != 256:
        raise ValueError('Invalid indexed draw context')
    output = bytearray(destination)
    for y, commands in enumerate(scanlines(data, width, height)):
        for x, count, kind, literal in commands:
            start = y * width + x
            if kind == 0:
                output[start:start + count] = literal
            elif kind == 2:
                output[start:start + count] = bytes([fill]) * count
            elif kind == 3:
                output[start:start + count] = bytes(shade[v] for v in output[start:start + count])
    return bytes(output)


def inspect(data, width, height):
    rows = scanlines(data, width, height)
    totals = [0] * 4
    for row in rows:
        for _, count, kind, _ in row:
            totals[kind] += count
    return dict(encoding='row-offset-u16/rle6', literal_pixels=totals[0],
                skip_pixels=totals[1], fill_pixels=totals[2], shade_pixels=totals[3],
                context_required=bool(totals[2] or totals[3]),
                validation='bounded scanline structure; palette and native clipping not reproduced')


def draw_surface(data, width, height, destination, surface_width, surface_height,
                 position, origin, clip, fill, shade, remap=None, bottom_up=False, in_place=False):
    """Draw at an anchor into an indexed surface with an inclusive clip rectangle.

    Origin and position are signed coordinates. bottom_up describes destination
    row storage, not a sprite flip. remap applies only to literal source pixels.
    Native 16-bit arithmetic overflow and malformed native buffers are excluded.
    """
    if not 1 <= surface_width <= 8192 or not 1 <= surface_height <= 8192 or surface_width*surface_height>64*1024*1024:
        raise ValueError('Invalid surface dimensions')
    if len(destination) != surface_width * surface_height or not 0 <= fill <= 255 or len(shade) != 256:
        raise ValueError('Invalid surface draw context')
    if remap is not None and len(remap) != 256:
        raise ValueError('Invalid literal remap')
    if len(position) != 2 or len(origin) != 2 or len(clip) != 4:
        raise ValueError('Invalid surface coordinates')
    left, top = position[0] - origin[0], position[1] - origin[1]
    if any(not -32768 <= v <= 32767 for v in (*position, *origin, left, top, left + width, top + height)):
        raise ValueError('Native word coordinate overflow is unsupported')
    cl, ct, cr, cb = clip
    if not 0 <= cl <= cr < surface_width or not 0 <= ct <= cb < surface_height:
        raise ValueError('Clip outside surface')
    if in_place and not isinstance(destination,bytearray):raise ValueError('In-place destination must be bytearray')
    output = destination if in_place else bytearray(destination)
    for y, commands in enumerate(scanlines(data, width, height)):
        dy = top + y
        if not ct <= dy <= cb:
            continue
        storage_y = surface_height - 1 - dy if bottom_up else dy
        for x, count, kind, literal in commands:
            first, end = max(left + x, cl), min(left + x + count, cr + 1)
            if first >= end or kind == 1:
                continue
            start = storage_y * surface_width + first
            n = end - first
            if kind == 0:
                skip = first - left - x
                values = literal[skip:skip + n]
                output[start:start + n] = values if remap is None else bytes(remap[v] for v in values)
            elif kind == 2:
                output[start:start + n] = bytes([fill]) * n
            else:
                output[start:start + n] = bytes(shade[v] for v in output[start:start + n])
    return output if in_place else bytes(output)


def draw_masked_surface(source, mask, destination, surface_width, surface_height,
                        position, mask_position, clip, fill, shade, remap=None, bottom_up=False, in_place=False):
    """Inline mask RLE: literal colours, skip, source-copy and background shade.

    source/mask are (payload, width, height, origin) tuples. Mask fill runs
    invoke the source scanline; they do not mean an opaque rectangular alpha.
    """
    data,w,h,origin=source;md,mw,mh,mo=mask
    # Reuse the bounded surface context checks before masked traversal.
    draw_surface(b'',0,0,destination,surface_width,surface_height,position,origin,clip,fill,shade,remap,bottom_up,in_place)
    rows=scanlines(data,w,h); masks=scanlines(md,mw,mh)
    sx,sy=position[0]-origin[0],position[1]-origin[1]
    mx,my=mask_position[0]-mo[0],mask_position[1]-mo[1]
    cl,ct,cr,cb=clip;out=destination if in_place else bytearray(destination)
    for y,commands in enumerate(masks):
        dy=my+y
        if not ct<=dy<=cb:continue
        row_index=dy-sy
        source_row={}
        if 0<=row_index<h:
            for x,n,k,literal in rows[row_index]:
                for j in range(n):source_row[sx+x+j]=(k,literal[j] if k==0 else 0)
        storage_y=surface_height-1-dy if bottom_up else dy
        for x,n,kind,literal in commands:
            for j in range(n):
                dx=mx+x+j
                if not cl<=dx<=cr or kind==1:continue
                at=storage_y*surface_width+dx
                if kind==0:out[at]=literal[j] if remap is None else remap[literal[j]]
                elif kind==3:out[at]=shade[out[at]]
                else:
                    k,value=source_row.get(dx,(1,0))
                    if k==0:out[at]=value
                    elif k==2:out[at]=fill
                    elif k==3:out[at]=shade[out[at]]
    return out if in_place else bytes(out)
