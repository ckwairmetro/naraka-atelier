"""Keep unchanged original compressed blocks when authoring a copied bundle."""
import struct
import lz4.block
from build_body_alias_candidate import unpack_logical


def pack_preserving(original, nodes, data, output):
    old_data, info = unpack_logical(original)
    raw = original.read_bytes()
    if data == old_data and nodes == info['nodes']:
        output.write_bytes(raw)
        return {'no_op_byte_identical': True, 'blocks_reused': len(info['blocks'])}
    field = raw.index(b'\0', raw.index(b'\0', 12)+1)+1
    old_size, _, _, flags = struct.unpack_from('>QIII', raw, field)
    if old_size != len(raw)+30 or flags != 582:
        raise ValueError('Unsupported custom header')
    pos = (4096+info['info_consumed']+4095)//4096*4096
    logical_pos = 0
    chunks, reused = [], 0
    for size, compressed_size, codec in info['blocks']:
        new_block = data[logical_pos:logical_pos+size]
        if len(new_block) != size:
            raise ValueError('Shrinking the original logical allocation is unsupported')
        if new_block == old_data[logical_pos:logical_pos+size]:
            compressed = raw[pos:pos+compressed_size]
            new_codec = codec
            reused += 1
        else:
            if codec not in (0, 6):
                raise ValueError('Changed block has an unverified codec')
            compressed = lz4.block.compress(new_block, mode='high_compression', compression=12, store_size=False)
            new_codec = 6
            if len(compressed) >= size:
                compressed, new_codec = new_block, 0
        chunks.append((size, compressed, new_codec))
        logical_pos += size
        pos = (pos+compressed_size+4095)//4096*4096
    for start in range(logical_pos, len(data), 131072):
        block = data[start:start+131072]
        compressed = lz4.block.compress(block, mode='high_compression', compression=12, store_size=False)
        codec = 6
        if len(compressed) >= len(block):
            compressed, codec = block, 0
        chunks.append((len(block), compressed, codec))
    meta = bytearray(16)+struct.pack('>I', len(chunks))
    for size, compressed, codec in chunks:
        meta += struct.pack('>IIH', size, len(compressed), codec)
    meta += struct.pack('>I', len(nodes))
    for offset, size, node_flags, name in nodes:
        meta += struct.pack('>QQI', offset, size, node_flags)+name.encode('latin1')+b'\0'
    meta += bytes((-len(meta)) % 4096)
    cm = lz4.block.compress(bytes(meta), mode='high_compression', compression=12, store_size=False)
    data_start = (4096+len(cm)+2+4095)//4096*4096
    total = data_start+sum((len(b)+4095)//4096*4096 for _, b, _ in chunks)
    header = bytearray(raw[:4096])
    struct.pack_into('>QIII', header, field, total+30, len(cm)+150, len(meta)+130, flags)
    with output.open('wb') as f:
        f.write(header); f.write(cm); f.write(bytes(data_start-f.tell()))
        for _, compressed, _ in chunks:
            f.write(compressed); f.write(bytes((-f.tell()) % 4096))
    reread, check = unpack_logical(output)
    if reread != data or check['nodes'] != nodes or output.stat().st_size != total:
        raise ValueError('Authored custom bundle failed full roundtrip')
    return {'blocks_reused': reused, 'blocks_changed': len(info['blocks'])-reused,
            'blocks_appended': len(chunks)-len(info['blocks']), 'physical_size': total,
            'logical_roundtrip_exact': True, 'node_roundtrip_exact': True}