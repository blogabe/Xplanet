"""Bounded inert PNG normalization shared by previews and frozen icons."""
import struct,zlib

def normalize_png(raw, *, byte_limit, dimension, pixels_limit, decode_limit):
    """Allow only bounded PNG container chunks; strip ancillary metadata.

    This checks container CRC/dimensions, not full image decoding or scene identity.
    No image parser or renderer is executed while importing.
    """
    if not 33 <= len(raw) <= byte_limit or raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Preview must be a bounded PNG.')
    output = bytearray(raw[:8]); pos = 8; count = 0; seen_data = False; data_ended = False
    compressed = bytearray(); expected = 0; palette=0; transparency=False
    while pos < len(raw):
        if pos + 12 > len(raw):
            raise ValueError('Truncated preview PNG.')
        size = int.from_bytes(raw[pos:pos+4], 'big'); kind = raw[pos+4:pos+8]; end = pos + 12 + size
        count += 1
        if end > len(raw) or count > 4096 or zlib.crc32(raw[pos+4:end-4]) & 0xffffffff != int.from_bytes(raw[end-4:end], 'big'):
            raise ValueError('Invalid preview PNG chunks.')
        if count == 1:
            if kind != b'IHDR' or size != 13:
                raise ValueError('Missing preview dimensions.')
            width, height = struct.unpack('>II', raw[pos+8:pos+16])
            if not 1 <= width <= dimension or not 1 <= height <= dimension or width * height > pixels_limit:
                raise ValueError('Preview exceeds supported dimensions.')
            depth, colour, compression, filtering, interlace = raw[pos+16:pos+21]
            channels = {0:1, 2:3, 3:1, 4:2, 6:4}.get(colour)
            allowed = {0:(1,2,4,8,16), 2:(8,16), 3:(1,2,4,8), 4:(8,16), 6:(8,16)}
            if channels is None or depth not in allowed[colour] or compression or filtering or interlace:
                raise ValueError('Preview requires supported noninterlaced PNG pixels.')
            stride = (width * channels * depth + 7) // 8 + 1
            expected = stride * height
            if expected > decode_limit: raise ValueError('Preview pixels exceed the decoding bound.')
        elif kind == b'IHDR':
            raise ValueError('Duplicate preview header.')
        if kind == b'PLTE':
            if palette or transparency or seen_data or colour in (0,4) or not 3<=size<=768 or size%3 or colour==3 and size//3>2**depth:
                raise ValueError('Invalid PNG palette presence, order or length.')
            palette=size//3
        if kind == b'tRNS':
            if transparency or seen_data or colour not in (0,2,3):raise ValueError('Invalid PNG transparency presence or order.')
            data=raw[pos+8:end-4]
            if colour==3 and (not palette or not 1<=size<=palette):raise ValueError('Indexed transparency requires a preceding matching palette.')
            if colour in (0,2) and (size!=(2 if colour==0 else 6) or any(int.from_bytes(data[i:i+2],'big')>=2**depth for i in range(0,size,2))):raise ValueError('Invalid PNG transparent sample.')
            transparency=True
        if kind == b'IDAT':
            if colour==3 and not palette:raise ValueError('Indexed PNG requires a preceding palette.')
            if data_ended: raise ValueError('Nonconsecutive PNG image data.')
            seen_data = True; compressed.extend(raw[pos+8:end-4])
        elif seen_data and kind != b'IEND': data_ended = True
        if kind in (b'IHDR', b'PLTE', b'IDAT', b'IEND', b'tRNS'):
            output.extend(raw[pos:end])
        elif not kind[0] & 32:
            raise ValueError('Unsupported critical PNG chunk.')
        pos = end
        if kind == b'IEND':
            if size or pos != len(raw) or not seen_data:
                raise ValueError('Invalid PNG ending.')
            try:
                decoder = zlib.decompressobj()
                pixels = decoder.decompress(compressed, expected + 1)
                if len(pixels) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                    raise ValueError('Preview pixel stream exceeds or differs from its dimensions.')
                if any(pixels[row * stride] > 4 for row in range(height)):
                    raise ValueError('Preview contains invalid scanline filters.')
            except zlib.error as exc:
                raise ValueError('Invalid preview pixel compression.') from exc
            return bytes(output)
    raise ValueError('Incomplete preview PNG.')
