"""Lossless native protobuf helpers, reused from the verified experiments."""

def varint(data, pos=0):
    n = shift = 0
    while pos < len(data) and shift < 70:
        b = data[pos]; pos += 1
        n |= (b & 127) << shift
        if not b & 128:
            return n, pos
        shift += 7
    raise ValueError('Invalid/truncated varint')

def fields(data):
    out, pos = [], 0
    while pos < len(data):
        start = pos
        key, pos = varint(data, pos)
        number, wire = key >> 3, key & 7
        if number == 0:
            raise ValueError('Zero protobuf field')
        if wire == 0:
            value, pos = varint(data, pos)
        elif wire in (1, 5):
            count = 8 if wire == 1 else 4
            value = data[pos:pos+count]; pos += count
        elif wire == 2:
            size, pos = varint(data, pos)
            value = data[pos:pos+size]; pos += size
            if len(value) != size:
                raise ValueError('Truncated field payload')
        else:
            raise ValueError(f'Unsupported wire type {wire}')
        if pos > len(data):
            raise ValueError('Truncated field')
        out.append({'number':number, 'wire':wire, 'value':value, 'raw':data[start:pos]})
    if b''.join(f['raw'] for f in out) != data:
        raise ValueError('Lossless parse differs')
    return out

def row_key(data):
    keys = [f for f in fields(data) if f['number'] == 1]
    if len(keys) != 1 or keys[0]['wire'] != 2:
        raise ValueError('Row key is ambiguous')
    return keys[0]['value'].decode('utf-8')

def vint(n):
    out = bytearray()
    while n > 127:
        out.append((n & 127) | 128); n >>= 7
    out.append(n)
    return bytes(out)

def delimited(number, payload):
    return vint(number*8+2)+vint(len(payload))+payload