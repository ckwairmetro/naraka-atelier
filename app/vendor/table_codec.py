import struct,json,copy
import game_tables
def uint(data, offset):
    return struct.unpack_from('<I', data, offset)[0]

def string_at(data, offset, end=None):
    end = len(data) if end is None else end
    length = uint(data, offset)
    stop = offset + 4 + length * 2
    if stop > end:
        raise ValueError(f'String at {offset} exceeds bounds')
    return data[offset + 4:stop].decode('utf-16le'), stop

def ddbl_encode(name, decoded):
    key = name.encode('ascii') + game_tables.COMMON_KEY + str(len(decoded)).encode('ascii')
    k = (key * (len(decoded) // len(key) + 1))[:len(decoded)]
    return bytes(a ^ b for a, b in zip(decoded, k))

def ddbl_decode(name, encoded):
    return game_tables.decode(name, encoded)

def rebuild_table(decoded_data, section, row_list, source_id, new_row_bytes):
    key_type = row_list[0]['keyType']
    if key_type != 'uint32':
        raise ValueError(f'Unexpected key type {key_type}')

    new_index = bytearray()
    new_bodies = bytearray()
    for row in row_list:
        old_body = decoded_data[row['offset']:row['offset'] + row['size']]
        body = new_row_bytes if row['id'] == source_id else old_body
        new_index += struct.pack('<II', row['id'], len(body))
        new_bodies += body

    count = section['count']
    new_section = struct.pack('<II', count, len(new_index)) + new_index + new_bodies

    all_sections = game_tables.sections(decoded_data)
    old_section_size = section['end'] - section['offset']
    offset_delta = len(new_section) - old_section_size

    _, dir_start = string_at(decoded_data, 8)
    dir_count = uint(decoded_data, dir_start)
    pos = dir_start + 4
    dir_entries = []
    for _ in range(dir_count):
        offset_val = uint(decoded_data, pos)
        name_val, next_pos = string_at(decoded_data, pos + 4)
        dir_entries.append({'pos': pos, 'offset': offset_val, 'name': name_val})
        pos = next_pos

    result = bytearray(decoded_data[:section['offset']]) + new_section + bytearray(decoded_data[section['end']:])

    for entry in dir_entries:
        if not entry['offset']:
            continue
        matched = next(s for s in all_sections if s['name'] == entry['name'] and s['offset'])
        if matched['offset'] > section['offset']:
            struct.pack_into('<I', result, entry['pos'], matched['offset'] + offset_delta)

    return bytes(result)
def load_table(sf, pid, name):
    obj = sf.objects[pid]
    tree = obj.read_typetree()
    if obj.save_typetree(copy.deepcopy(tree)) != obj.get_raw_data():
        raise ValueError(name + ' no-op serialization differs')
    raw = tree['m_Script'].encode('utf-8', errors='surrogateescape')
    decoded = ddbl_decode(name, raw)
    if ddbl_encode(name, decoded) != raw:
        raise ValueError(name + ' DDBL no-op failed')
    return obj, tree, decoded

def finish_table(obj, tree, name, patched):
    encoded = ddbl_encode(name, patched)
    if ddbl_decode(name, encoded) != patched:
        raise ValueError(name + ' patched DDBL roundtrip failed')
    tree['m_Script'] = encoded.decode('utf-8', errors='surrogateescape')
    return obj.save_typetree(tree)

def row_map(data, sec):
    if not sec['offset']:
        return {}
    return {r['id']: data[r['offset']:r['offset']+r['size']] for r in game_tables.rows(data, sec)}

def changed_rows(before, after):
    old = {s['name']: s for s in game_tables.sections(before)}
    changed = []
    for sec in game_tables.sections(after):
        o, n = row_map(before, old[sec['name']]), row_map(after, sec)
        if o.keys() != n.keys():
            raise ValueError('Row inventory changed in ' + sec['name'])
        changed += [(sec['name'], k) for k, v in n.items() if v != o[k]]
    return sorted(changed)

def section_rows(data, name):
    sec = next(s for s in game_tables.sections(data) if s['name'] == name)
    rows = game_tables.rows(data, sec)
    return sec, rows, {r['id']: data[r['offset']:r['offset']+r['size']] for r in rows}
PRIM = {'int': ('<i', 4), 'float': ('<f', 4), 'short': ('<h', 2), 'long': ('<q', 8), 'bool': ('<?', 1)}
class RowDecoder:
    def __init__(self, schema, specs=None):
        self.schema = schema  # class name -> [[field, type], ...]
        self.specs = specs or {}
        self.cur = {}

    def value(self, t, b, p, path=''):
        if t.endswith('[]'):
            flag = b[p]; p += 1
            if not flag:
                return None, p
            fixed = self.cur.get(path, 'c')
            if fixed == 'c':
                n = struct.unpack_from('<i', b, p)[0]; p += 4
            else:
                n = fixed
            if n < 0 or n > 1_000_000:
                raise ValueError(f'bad array length {n}')
            out = []
            for _ in range(n):
                v, p = self.value(t[:-2], b, p, path + '/[]'); out.append(v)
            return out, p
        if t == 'string':
            n = struct.unpack_from('<i', b, p)[0]; p += 4
            if n < 0 or p + 2 * n > len(b):
                raise ValueError(f'bad string length {n}')
            return b[p:p + 2 * n].decode('utf-16le', errors='surrogatepass'), p + 2 * n
        if t in PRIM:
            fmt, sz = PRIM[t]
            if p + sz > len(b):
                raise ValueError('read past row end')
            v = struct.unpack_from(fmt, b, p)[0]
            if t == 'bool' and b[p] not in (0, 1):
                raise ValueError('non-boolean byte')
            return v, p + sz
        cls = t.split('.')[-1]
        if cls not in self.schema:
            raise KeyError(f'no schema for {t}')
        flag = b[p]; p += 1
        if not flag:
            return None, p
        return self.obj(cls, b, p, path)

    def obj(self, cls, b, p, path=''):
        o = {}
        for name, t in self.schema[cls]:
            o[name], p = self.value(t, b, p, f'{path}.{name}' if path else name)
        return o, p

    def row(self, cls, b):
        self.cur = self.specs.get(cls, {})
        o, p = self.obj(cls, b, 0)
        if p != len(b):
            raise ValueError(f'consumed {p} of {len(b)} bytes')
        return o
def field_spans(decoder, schema, cls, payload):
    decoder.cur = decoder.specs.get(cls, {})
    result, pos = {}, 0
    for name, typ in schema[cls]:
        start = pos
        value, pos = decoder.value(typ, payload, pos, name)
        result[name] = (start, pos, value)
    if pos != len(payload):
        raise ValueError('Schema did not consume full row')
    return result