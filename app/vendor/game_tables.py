"""Read the installed game's DDBL tables without substituting unknown fields.

Exports decoded bytes, section/row indexes and length-prefixed string fields.
Field offsets are evidence, not inferred field names or foreign-key semantics.
The game installation is always opened read-only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

COMMON_KEY = b"95e09ae0bec948e4fa73959f695cd3a65a6d707339449e1d44ac21685ab746beb334b3a72a667541e9e263bf8a04dbd402c8edaf80e5d4a34d3f0995251445f81c4a67f9438c54c43a0511b5fa72c97d61b0d06a09b03713935d9638218c2697e54544a0fce9f3910b117e09caebde13d40aa76d6314784692c31f82b98ad83e82ec5c8cf69a62556e64d0c9604e5cf13d79be3fe7dc06d701c63e220402cefc35629d96c425d2e4b5a85b7d2576e083ae026c63815714baf5ee9396bc54424b701d0d0228c93eb9b25f7c973fa40678fa54873b5e0212430b85c99df80e79798cfc31cc96f1e3a892946da0097e8c33a7d23434110c6eed74b71065bea1715d191b81e536a4100b21693dc62ec96b8baa8c21c076729ce15f994fe1a38a407"
DEFAULT_TABLES = (
    'CharacterConfig,HeroFashion,FashionConfig,HairItem,HairConfig,HeroFace,'
    'AvatarFace,AutoAnimationClip,AutoAnimatorStates,ShowOffItemConfig,'
    'StagePreview,PhotoStudioAssetConfig,GameplayExtraPhysics,HeroLobbyShow'
)


def uint(data, offset):
    if offset < 0 or offset + 4 > len(data):
        raise ValueError(f'Integer outside table at {offset}')
    return struct.unpack_from('<I', data, offset)[0]


def string(data, offset, end=None):
    end = len(data) if end is None else end
    length = uint(data, offset)
    stop = offset + 4 + length * 2
    if stop > end:
        raise ValueError(f'String outside bounds at {offset}')
    return data[offset + 4:stop].decode('utf-16le'), stop


def decode(name, encoded):
    key = name.encode('ascii') + COMMON_KEY + str(len(encoded)).encode('ascii')
    decoded = bytes(v ^ key[i % len(key)] for i, v in enumerate(encoded))
    if decoded[:8] != b'DDBL\x01\x00\x00\x00':
        raise ValueError(f'{name}: unsupported DDBL header')
    actual, _ = string(decoded, 8)
    if actual != name:
        raise ValueError(f'{name}: table identity mismatch ({actual!r})')
    return decoded


def sections(data):
    _, pos = string(data, 8)
    count = uint(data, pos)
    pos += 4
    entries = []
    for _ in range(count):
        start = uint(data, pos)
        name, pos = string(data, pos + 4)
        entries.append({'name': name, 'offset': start})
    active = [e for e in entries if e['offset']]
    if active and active[0]['offset'] != pos:
        raise ValueError('Section directory does not end at first section')
    for i, entry in enumerate(active):
        start = entry['offset']
        end = active[i + 1]['offset'] if i + 1 < len(active) else len(data)
        if not pos <= start < end <= len(data):
            raise ValueError('Invalid section bounds')
        entry.update(end=end, count=uint(data, start), indexBytes=uint(data, start + 4))
    return entries


def rows(data, section):
    if not section['offset']:
        return []
    pos = section['offset'] + 8
    count, index_bytes = section['count'], section['indexBytes']
    body = pos + index_bytes
    if body > section['end']:
        raise ValueError('Index exceeds section')
    if count == 0:
        if body != section['end']:
            raise ValueError('Empty section contains unindexed bytes')
        return []
    kind = 'uint32' if index_bytes == count * 8 else 'uint64' if index_bytes == count * 12 else 'string'
    result = []
    for _ in range(count):
        if kind == 'uint32':
            identity = uint(data, pos)
            pos += 4
        elif kind == 'uint64':
            identity = str(struct.unpack_from('<Q', data, pos)[0])
            pos += 8
        else:
            identity, pos = string(data, pos, section['offset'] + 8 + index_bytes)
        size = uint(data, pos)
        pos += 4
        if body + size > section['end']:
            raise ValueError('Row exceeds section')
        # Every supported row repeats its index key at the beginning.
        if kind == 'string':
            actual, _ = string(data, body, body + size)
        elif kind == 'uint64':
            actual = str(struct.unpack_from('<Q', data, body)[0])
        else:
            actual = uint(data, body)
        if actual != identity:
            raise ValueError(f'Index/row key mismatch at {body}: {identity!r} / {actual!r}')
        result.append({'id': identity, 'keyType': kind, 'offset': body, 'size': size})
        body += size
    if pos != section['offset'] + 8 + index_bytes or body != section['end']:
        raise ValueError('Row/index boundaries do not account for all section bytes')
    return result


def text_fields(row):
    """Extract only declared, bounded ASCII UTF-16 strings, including unaligned fields.

    These fields have verified byte bounds. Their names/meanings remain unspecified.
    Non-ASCII/localized strings stay losslessly available in the decoded table.
    """
    fields = []
    stop = 0
    for pos in range(max(0, len(row) - 3)):
        if pos < stop:
            continue
        n = uint(row, pos)
        if not 4 <= n <= 4096 or pos + 4 + 2 * n > len(row):
            continue
        raw = row[pos + 4:pos + 4 + 2 * n]
        if all(raw[k + 1] == 0 and 32 <= raw[k] < 127 for k in range(0, len(raw), 2)):
            stop = pos + 4 + 2 * n
            fields.append({'offset': pos, 'value': raw.decode('utf-16le')})
    return fields


def load_source():
    from nrk_env import Resolver
    resolver = Resolver()
    # Validate the owning AssetBundle container, rather than trusting the heuristic catalog.
    inv = {v.replace('\\', '/'): k for k, v in resolver.index.items()}
    sf = resolver.load_cab(inv['f/a/fab72152d7112058'])
    ab = next(o.read_typetree() for o in sf.objects.values() if o.type.name == 'AssetBundle')
    for path, reference in ab['m_Container']:
        if not path.startswith('assets/raw_resources/xls-bytes/'):
            continue
        obj, owner = resolver.get(sf, reference['asset'])
        if obj is None or obj.type.name != 'TextAsset':
            raise ValueError(f'Invalid TextAsset reference: {path}')
        tree = obj.read_typetree()
        value = tree['m_Script']
        encoded = value.encode('utf8', errors='surrogateescape') if isinstance(value, str) else bytes(value)
        yield path, obj.path_id, tree['m_Name'], encoded


def export(out, wanted):
    out.mkdir(parents=True, exist_ok=True)
    inventory = {'bundle': 'f/a/fab72152d7112058', 'files': [], 'format': 'DDBL v1',
                 'schemaPolicy': 'Unidentified fields and joins are never assigned inferred semantics.'}
    for path, path_id, name, encoded in load_source():
        data = decode(name, encoded)
        directory = sections(data)
        record = {'name': name, 'sourcePath': path, 'sourcePathId': path_id,
                  'encodedSha256': hashlib.sha256(encoded).hexdigest(),
                  'decodedSha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'sections': directory}
        if name in wanted:
            (out / f'{name}.ddbl').write_bytes(data)
            index = {'source': {k: v for k, v in record.items() if k != 'sections'}, 'sections': []}
            for section in directory:
                exported = dict(section)
                try:
                    exported['rows'] = rows(data, section)
                    for row in exported['rows']:
                        payload = data[row['offset']:row['offset'] + row['size']]
                        row['sha256'] = hashlib.sha256(payload).hexdigest()
                        row['strings'] = text_fields(payload)
                    exported['indexValidated'] = True
                except (ValueError, struct.error, UnicodeError) as exc:
                    exported['indexValidated'] = False
                    exported['error'] = str(exc)
                    # Retain original section bytes. Do not silently invent an index schema.
                    exported.pop('rows', None)
                index['sections'].append(exported)
            (out / f'{name}.json').write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf8')
            print(name, sum(len(s.get('rows', [])) for s in index['sections']), 'validated rows')
        inventory['files'].append(record)
    inventory['fileCount'] = len(inventory['files'])
    inventory['sectionCount'] = sum(len(f['sections']) for f in inventory['files'])
    (out / 'inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf8')
    print('Inventory:', inventory['fileCount'], 'files,', inventory['sectionCount'], 'sections')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--tables', default=DEFAULT_TABLES)
    args = parser.parse_args()
    export(args.out, set(args.tables.split(',')))