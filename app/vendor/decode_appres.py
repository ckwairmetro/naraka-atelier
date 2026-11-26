"""Decode the original AppRes data using the inspected native reader layout.

Read-only: reconstruction is compared in memory and never written to the game.
"""
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GAME = Path(os.environ.get("NARAKA_STREAMING_ASSETS", "NARAKA_STREAMING_ASSETS"))


class Reader:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def scalar(self, fmt):
        size = struct.calcsize('<' + fmt)
        if self.offset + size > len(self.data):
            raise ValueError(f'Truncated scalar at {self.offset}')
        value = struct.unpack_from('<' + fmt, self.data, self.offset)[0]
        self.offset += size
        return value

    def string(self):
        length = 0
        for shift in range(0, 35, 7):
            byte = self.scalar('B')
            length |= (byte & 127) << shift
            if byte < 128:
                break
        else:
            raise ValueError('Invalid 7-bit string length')
        if length > len(self.data) - self.offset:
            raise ValueError(f'Truncated string at {self.offset}: {length}')
        value = self.data[self.offset:self.offset + length].decode('utf-8', errors='strict')
        self.offset += length
        return value


def encode_string(text):
    data = text.encode('utf-8')
    length, prefix = len(data), bytearray()
    while length >= 128:
        prefix.append((length & 127) | 128)
        length >>= 7
    prefix.append(length)
    return bytes(prefix) + data


def record(reader, kind):
    item = {'offset': reader.offset}
    for key in ('patch_status', 'classify', 'file_mode'):
        item[key] = reader.scalar('B')
    if kind == 'bundle':
        item['crc'] = reader.scalar('I')
        item['bundle_hash'] = reader.string()
        item['file_hash'] = reader.string()
        item['file_size'] = reader.scalar('i')
        item['bundle_name'] = reader.string()
    else:
        item['file_name'] = reader.string()
        item['hash'] = reader.string()
        item['file_size'] = reader.scalar('i')
    item['patch_version'] = reader.scalar('i')
    item['res_version'] = reader.scalar('i')
    if kind == 'bundle':
        item['assets'] = [reader.string() for _ in range(reader.scalar('H'))]
    return item


def encode_record(item, kind):
    data = bytearray(struct.pack('<BBB', *(item[k] for k in ('patch_status', 'classify', 'file_mode'))))
    if kind == 'bundle':
        data += struct.pack('<I', item['crc'])
        data += encode_string(item['bundle_hash']) + encode_string(item['file_hash'])
        data += struct.pack('<i', item['file_size']) + encode_string(item['bundle_name'])
    else:
        data += encode_string(item['file_name']) + encode_string(item['hash'])
        data += struct.pack('<i', item['file_size'])
    data += struct.pack('<ii', item['patch_version'], item['res_version'])
    if kind == 'bundle':
        data += struct.pack('<H', len(item['assets']))
        for asset in item['assets']:
            data += encode_string(asset)
    return data


def decode(data):
    r = Reader(data)
    header = {'format_word': r.scalar('i')}
    for key in ('play_build', 'build_time', 'version', 'build_target', 'build_name'):
        header[key] = r.string()
    for key, fmt in (('patch_index', 'i'), ('ab_type', 'i'), ('size', 'q'), ('index', 'i')):
        header[key] = r.scalar(fmt)
    bundles = [record(r, 'bundle') for _ in range(r.scalar('I'))]
    for bundle in bundles:
        bundle['dependencies'] = []
        for _ in range(r.scalar('H')):
            tag = r.scalar('B')
            value = r.string() if tag == 6 else r.scalar('i')
            if tag != 6 and not 0 <= value < len(bundles):
                raise ValueError(f'Invalid dependency index {value}')
            bundle['dependencies'].append({'tag': tag, 'value': value})
    sync_bundles = [r.scalar('i') for _ in range(r.scalar('I'))]
    rawfiles = [record(r, 'raw') for _ in range(r.scalar('I'))]
    sync_raw = [r.scalar('i') for _ in range(r.scalar('I'))]
    if r.offset != len(data):
        raise ValueError(f'Decoder consumed {r.offset} of {len(data)} bytes')
    if any(not 0 <= i < len(bundles) for i in sync_bundles):
        raise ValueError('Invalid sync bundle reference')
    if any(not 0 <= i < len(rawfiles) for i in sync_raw):
        raise ValueError('Invalid sync raw reference')
    return {'header': header, 'bundles': bundles, 'sync_bundles': sync_bundles,
            'rawfiles': rawfiles, 'sync_rawfiles': sync_raw, 'consumed_bytes': r.offset}


def encode(decoded):
    h = decoded['header']
    result = bytearray(struct.pack('<i', h['format_word']))
    for key in ('play_build', 'build_time', 'version', 'build_target', 'build_name'):
        result += encode_string(h[key])
    result += struct.pack('<iiqi', h['patch_index'], h['ab_type'], h['size'], h['index'])
    result += struct.pack('<I', len(decoded['bundles']))
    for item in decoded['bundles']:
        result += encode_record(item, 'bundle')
    for item in decoded['bundles']:
        result += struct.pack('<H', len(item['dependencies']))
        for dep in item['dependencies']:
            result += struct.pack('<B', dep['tag'])
            result += encode_string(dep['value']) if dep['tag'] == 6 else struct.pack('<i', dep['value'])
    result += struct.pack('<I', len(decoded['sync_bundles']))
    for index in decoded['sync_bundles']:
        result += struct.pack('<i', index)
    result += struct.pack('<I', len(decoded['rawfiles']))
    for item in decoded['rawfiles']:
        result += encode_record(item, 'raw')
    result += struct.pack('<I', len(decoded['sync_rawfiles']))
    for index in decoded['sync_rawfiles']:
        result += struct.pack('<i', index)
    return result


def main():
    with zipfile.ZipFile(GAME / 'AppRes.info') as archive:
        data = archive.read('data')
    decoded = decode(data)
    roundtrip = encode(decoded)
    if roundtrip != data:
        raise ValueError('Decoded fields did not reproduce the original bytes')
    bundles = decoded['bundles']
    selected = [b for b in bundles if any('ch_f_hanhaimomin' in a and
                ('hair_lv_ss1' in a or 'hair_lv_b0' in a or
                 a.endswith('/ch_f_hanhaimomin_lv_ss1_hg.prefab') or
                 a.endswith('/ch_f_hanhaimomin_lv_b0.prefab')) for a in b['assets'])]
    by_name = {b['bundle_name']: b for b in bundles}
    for bundle in selected:
        path = GAME / bundle['bundle_name']
        info = {'exists': path.is_file()}
        if info['exists']:
            md5_hasher, sha_hasher = hashlib.md5(), hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    md5_hasher.update(chunk)
                    sha_hasher.update(chunk)
            md5 = md5_hasher.hexdigest()
            info.update(bytes=path.stat().st_size, sha256=sha_hasher.hexdigest(), md5=md5,
                        size_matches=path.stat().st_size == bundle['file_size'],
                        file_hash_matches_md5=bundle['file_hash'].lower() == md5)
        bundle['disk_observation'] = info
        bundle['resolved_dependency_names'] = [d['value'] if d['tag'] == 6 else bundles[d['value']]['bundle_name']
                                                for d in bundle['dependencies']]
    summary = {'source': str(GAME / 'AppRes.info'), 'data_sha256': hashlib.sha256(data).hexdigest(),
               'reader_basis': 'Inspected FileUtils.ParseAppResVO, ParseABFile, ParseRawFile; BinaryReader virtual slots from prior metadata',
               'header': decoded['header'], 'consumed_bytes': decoded['consumed_bytes'],
               'roundtrip_identical': True, 'bundle_count': len(bundles), 'rawfile_count': len(decoded['rawfiles']),
               'sync_bundle_count': len(decoded['sync_bundles']), 'sync_rawfile_count': len(decoded['sync_rawfiles']),
               'asset_count': sum(len(b['assets']) for b in bundles),
               'unique_asset_count': len({a for b in bundles for a in b['assets']}),
               'bundle_name_count': len(by_name),
               'bundle_classify_counts': dict(Counter(b['classify'] for b in bundles)),
               'bundle_file_mode_counts': dict(Counter(b['file_mode'] for b in bundles)),
               'selected_bundle_names': [b['bundle_name'] for b in selected],
               'limitations': ['Decoded recorded fields are not proof of runtime enforcement.',
                               'No game/index modification or execution.',
                               'The encoder is used only for an in-memory byte-for-byte parser validation.']}
    reports = ROOT / 'reports'
    (reports / 'appres-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    (reports / 'matari-bundle-records.json').write_text(json.dumps(selected, indent=2), encoding='utf-8')
    with gzip.open(reports / 'appres-decoded.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump(decoded, stream, separators=(',', ':'))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
