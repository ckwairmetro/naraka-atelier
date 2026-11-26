"""Patch serialized objects without reserializing unrelated metadata or payloads.

Only supports verified little-endian version-21, single-node files. This is a
format-preservation utility, not a claim of native acceptance.
"""
import struct
from build_body_alias_candidate import load_sf, sha, semantic_metadata


def replace_objects(original, replacements):
    if len(original) < 20 or struct.unpack_from('>I', original, 8)[0] != 21:
        raise ValueError('Unsupported serialized-file version')
    sf = load_sf(original)
    h = sf.header
    if h.version != 21 or h.endian != '<' or h.file_size != len(original):
        raise ValueError('Unsupported serialized-file layout')
    if not set(replacements).issubset(sf.objects):
        raise ValueError('Unknown object ID')
    if not replacements:
        return original, {'changed_objects': [], 'old_offsets_preserved': True}
    out = bytearray(original)
    edited_spans = [(4, 8)]  # big-endian file size in the serialized header
    for pid, payload in replacements.items():
        obj = sf.objects[pid]
        # Validate a unique exact directory record, never guess its location.
        needle = struct.pack('<qIIi', pid, obj.byte_start-h.data_offset,
                             obj.byte_size, obj.type_id)
        at = original.find(needle, 20, h.data_offset)
        if at < 0 or original.find(needle, at+1, h.data_offset) >= 0 or at % 4:
            raise ValueError('Object directory record is absent or ambiguous')
        if payload == obj.get_raw_data():
            continue
        if len(payload) <= obj.byte_size:
            # Keep the existing allocation. Object length may change, but its
            # trailing old allocation remains outside the new object range.
            start = obj.byte_start
            out[start:start+len(payload)] = payload
            edited_spans.append((start, start+len(payload)))
        else:
            out.extend(bytes((-len(out)) % 8))
            start = len(out)
            out.extend(payload)
        struct.pack_into('<II', out, at+8, start-h.data_offset, len(payload))
        edited_spans.append((at+8, at+16))
    struct.pack_into('>I', out, 4, len(out))
    result = bytes(out)
    check = load_sf(result)
    if set(check.objects) != set(sf.objects) or semantic_metadata(check) != semantic_metadata(sf):
        raise ValueError('Object inventory or semantic metadata changed')
    changes = []
    for pid, old in sf.objects.items():
        new = check.objects[pid]
        expected = replacements.get(pid, old.get_raw_data())
        if new.get_raw_data() != expected or new.type_id != old.type_id:
            raise ValueError('Object payload/type mismatch')
        if old.get_raw_data() != expected:
            changes.append(pid)
        elif (old.byte_start, old.byte_size) != (new.byte_start, new.byte_size):
            raise ValueError('Unchanged object was relocated')
    # Byte-for-byte proof outside explicitly permitted edits.
    pos = 0
    for a, b in sorted(edited_spans):
        if a > pos and result[pos:a] != original[pos:a]:
            raise ValueError('Unexpected byte change outside approved spans')
        pos = max(pos, b)
    if result[pos:len(original)] != original[pos:]:
        raise ValueError('Unexpected unchanged tail edit')
    return result, {'changed_objects': sorted(changes),
                    'old_offsets_preserved': True, 'unrelated_bytes_identical': True,
                    'old_size': len(original), 'new_size': len(result),
                    'edited_spans': edited_spans, 'sha256': sha(result)}