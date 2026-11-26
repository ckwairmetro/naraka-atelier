"""Build and verify a Matari body-alias bundle ON PROJECT COPIES ONLY.

This is a format/asset-lookup experiment, not an installed mod. No live process
access, game writes, index deployment or ownership changes are performed.
"""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
from naraka_extract import GAME, read_info, decompress_block
import lz4.block
import UnityPy
from UnityPy.streams import EndianBinaryWriter

NAME = '6/1/61f5d992abed2fb8'
CAB = 'cab-0d366caf8c2871655f06445f1a5605bd'
PREFIX = 'assets/res/prefab/actor_visual_part/ch_f_hanhaimomin/'
SOURCE_PATH = PREFIX + 'ch_f_hanhaimomin_lv_b0.prefab'
TARGET_PATH = PREFIX + 'ch_f_hanhaimomin_lv_ss1_hg.prefab'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_sf(raw):
    env = UnityPy.load(raw)
    return next(f for f in env.files.values() if hasattr(f, 'objects'))


def semantic_metadata(sf):
    def serialized(items, kind):
        w = EndianBinaryWriter(endian=sf.header.endian)
        for item in items or []:
            if kind == 'type':
                item.write(sf, w, False)
            elif kind == 'ref':
                item.write(sf, w, True)
            elif kind == 'script':
                item.write(sf.header, w)
            else:
                item.write(sf.header, w)
        return sha(w.bytes)
    return {'version': sf.header.version, 'endian': sf.header.endian,
            'unity_version': sf.unity_version, 'target_platform': sf._m_target_platform,
            'type_tree_enabled': sf._enable_type_tree,
            'types_sha256': serialized(sf.types, 'type'),
            'externals_sha256': serialized(sf.externals, 'external'),
            'scripts_sha256': serialized(sf.script_types, 'script'),
            'ref_types_sha256': serialized(sf.ref_types, 'ref'),
            'user_information': sf.userInformation}


def unpack_logical(path):
    info = read_info(str(path))
    pos = (4096 + info['info_consumed'] + 4095) // 4096 * 4096
    parts = []
    with path.open('rb') as f:
        for u, c, flags in info['blocks']:
            f.seek(pos)
            parts.append(decompress_block(f.read(c), u, flags))
            pos = (pos+c+4095)//4096*4096
    return b''.join(parts), info


def pack_candidate(original, nodes, data, output):
    # These arithmetic differences are observations from 67 installed bundles.
    # They are not a claim that the native engine accepts this authored file.
    with original.open('rb') as f:
        header = bytearray(f.read(4096))
    field = header.index(b'\0', header.index(b'\0', 12)+1)+1
    old_size, old_csz, old_usz, flags = struct.unpack_from('>QIII', header, field)
    if old_size != original.stat().st_size+30 or flags != 582:
        raise ValueError('Original header differs from surveyed layout')
    blocks, packed = [], []
    for offset in range(0, len(data), 131072):
        raw = data[offset:offset+131072]
        compressed = lz4.block.compress(raw, store_size=False)
        if len(compressed) >= len(raw):
            compressed, codec = raw, 0
        else:
            codec = 6
        blocks.append((len(raw), len(compressed), codec))
        packed.append(compressed)
    metadata = bytearray(16) + struct.pack('>I', len(blocks))
    for block in blocks:
        metadata += struct.pack('>IIH', *block)
    metadata += struct.pack('>I', len(nodes))
    for offset, size, flag, name in nodes:
        metadata += struct.pack('>QQI', offset, size, flag) + name.encode('latin1') + b'\0'
    metadata += bytes((-len(metadata)) % 4096)
    compressed_info = lz4.block.compress(bytes(metadata), store_size=False)
    data_start = (4096+len(compressed_info)+2+4095)//4096*4096
    total_size = data_start + sum((len(b)+4095)//4096*4096 for b in packed)
    struct.pack_into('>QIII', header, field, total_size+30,
                     len(compressed_info)+150, len(metadata)+130, flags)
    with output.open('wb') as f:
        f.write(header)
        f.write(compressed_info)
        f.write(bytes(data_start-f.tell()))
        for block in packed:
            f.write(block)
            f.write(bytes((-f.tell()) % 4096))
    if output.stat().st_size != total_size:
        raise ValueError('Candidate physical size mismatch')
    return {'physical_size': total_size, 'block_count': len(blocks),
            'metadata_compressed_size': len(compressed_info),
            'metadata_decoded_size': len(metadata)}


def main():
    out = ROOT / 'work/body-alias-candidate'
    out.mkdir(parents=True, exist_ok=True)
    with gzip.open(ROOT / 'reports/appres-decoded.json.gz', 'rt', encoding='utf-8') as f:
        manifest = json.load(f)
    record = next(b for b in manifest['bundles'] if b['bundle_name'] == NAME)
    original = Path(GAME) / NAME
    file_before = original.read_bytes()
    if hashlib.md5(file_before).hexdigest() != record['file_hash'] or len(file_before) != record['file_size']:
        raise ValueError('Installed input differs from verified manifest')
    original_sha = sha(file_before)
    del file_before
    logical, info = unpack_logical(original)
    if zlib.crc32(logical) != record['crc']:
        raise ValueError('Original logical CRC32 differs from manifest')
    if len(info['nodes']) != 2 or info['nodes'][0][0] != 0 or sum(n[1] for n in info['nodes']) != len(logical):
        raise ValueError('Expected contiguous CAB and resource nodes')
    cab_start, cab_size, cab_flags, cab_name = info['nodes'][0]
    if cab_name.lower() != CAB:
        raise ValueError('Unexpected serialized node')
    original_cab = logical[:cab_size]
    graph = json.loads((ROOT / 'reports/matari-asset-graph.json').read_text())
    if sha(original_cab) != graph['verified_cabs'][CAB]['serialized_sha256']:
        raise ValueError('Serialized source differs from prior current-game verification')
    sf = load_sf(original_cab)
    original_objects = {o.path_id: (o.type_id, sha(o.get_raw_data())) for o in sf.objects.values()}
    original_metadata = semantic_metadata(sf)
    bundle = next(o for o in sf.objects.values() if o.type.name == 'AssetBundle')
    container = bundle.read_typetree()
    original_container = copy.deepcopy(container)
    if any(path == SOURCE_PATH for path, entry in container['m_Container']):
        raise ValueError('Source alias already exists in target bundle')
    target_entries = [entry for path, entry in container['m_Container'] if path == TARGET_PATH]
    if len(target_entries) != 1:
        raise ValueError('Expected one target prefab entry')
    entry = copy.deepcopy(target_entries[0])
    if entry['asset']['m_FileID'] != 0:
        raise ValueError('Target root is not local to the selected CAB')
    container['m_Container'].append((SOURCE_PATH, entry))
    bundle.save_typetree(container)
    authored_cab = sf.save()
    check = load_sf(authored_cab)
    changed = []
    if set(check.objects) != set(original_objects) or semantic_metadata(check) != original_metadata:
        raise ValueError('Serialized object inventory or metadata changed')
    for o in check.objects.values():
        old_type, old_sha = original_objects[o.path_id]
        if o.type_id != old_type:
            raise ValueError('Object type changed')
        if sha(o.get_raw_data()) != old_sha:
            changed.append(o.path_id)
    if changed != [bundle.path_id]:
        raise ValueError(f'Unexpected modified object IDs: {changed}')
    after_container = check.objects[bundle.path_id].read_typetree()
    unchanged_entries = {path: value for path, value in after_container['m_Container'] if path != SOURCE_PATH}
    if after_container != container or unchanged_entries != dict(original_container['m_Container']):
        raise ValueError('Authored container differs on roundtrip')
    actual_alias = dict(after_container['m_Container'])[SOURCE_PATH]
    root = check.objects[actual_alias['asset']['m_PathID']]
    if root.type.name != 'GameObject' or root.read_typetree()['m_Name'] != 'ch_f_hanhaimomin_lv_ss1_hg':
        raise ValueError('Alias does not resolve to target GameObject')
    resource = logical[cab_size:]
    authored_logical = authored_cab + resource
    nodes = [(0, len(authored_cab), cab_flags, cab_name),
             (len(authored_cab), len(resource), info['nodes'][1][2], info['nodes'][1][3])]
    candidate = out / 'body-alias.bundle'
    packing = pack_candidate(original, nodes, authored_logical, candidate)
    decoded, candidate_info = unpack_logical(candidate)
    if decoded != authored_logical or candidate_info['nodes'] != nodes:
        raise ValueError('Repacked custom bundle does not decode identically')
    final_sf = load_sf(decoded[:len(authored_cab)])
    if final_sf.objects[root.path_id].get_raw_data() != check.objects[root.path_id].get_raw_data():
        raise ValueError('Target prefab raw bytes changed during packing')
    if sha(original.read_bytes()) != original_sha:
        raise ValueError('Installed input changed during experiment')
    candidate_bytes = candidate.read_bytes()
    report = {'scope': 'offline body-alias format experiment only',
              'applied': False, 'game_files_modified': False, 'native_engine_acceptance_tested': False,
              'candidate': str(candidate), 'original_bundle': NAME,
              'original_file_sha256': original_sha, 'candidate_sha256': sha(candidate_bytes),
              'candidate_md5': hashlib.md5(candidate_bytes).hexdigest(),
              'source_asset_alias': SOURCE_PATH, 'target_asset': TARGET_PATH,
              'target_root_path_id': root.path_id, 'target_root_name': root.read_typetree()['m_Name'],
              'object_count': len(original_objects), 'unchanged_raw_objects': len(original_objects)-1,
              'changed_object_ids': changed, 'serialized_metadata_preserved': True,
              'resource_stream_sha256': sha(resource), 'resource_stream_preserved': True,
              'original_crc32_matches_manifest': True,
              'candidate_logical_crc32': zlib.crc32(authored_logical),
              'packing': packing, 'candidate_roundtrip_identical': True,
              'limitations': ['Body only; hair and customization are not replaced.',
                              'AppRes still maps source asset to original source bundle; no index was deployed.',
                              'AppRes bundleHash meaning and native loader validation remain unresolved.',
                              'Sampled header arithmetic is reproduced; native acceptance is not demonstrated.',
                              'Alias substitution can affect every local character requesting this source path.',
                              'No visual, effect, gameplay, remote-client or frame-time parity result.']}
    (ROOT / 'reports/body-alias-candidate.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()