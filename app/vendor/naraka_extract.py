"""Naraka: Bladepoint asset tool (experimental). Requires: pip install lz4 UnityPy numpy
Usage:
  python naraka_extract.py find   <regex>                      search the AppRes.info manifest for asset paths
  python naraka_extract.py unpack <bundle_file> <out_dir>      convert a Naraka bundle into standard CAB/.resS files
  python naraka_extract.py export <unpacked_dir> <out_dir>     dump Texture2D -> PNG and Mesh -> OBJ
"""
# Naraka bundle reader (experimental)
import sys, struct, lz4.block
def lz4_lenient(src, cap, with_consumed=False):
    i=0; out=bytearray()
    while i<len(src) and len(out)<cap:
        t=src[i]; i+=1; L=t>>4
        if L==15:
            while True:
                b=src[i]; i+=1; L+=b
                if b!=255: break
        out+=src[i:i+L]; i+=L
        if i>=len(src) or len(out)>=cap: break
        off=src[i]|(src[i+1]<<8); i+=2
        if off==0: break
        M=t&15
        if M==15:
            while True:
                b=src[i]; i+=1; M+=b
                if b!=255: break
        M+=4
        for _ in range(M): out.append(out[-off])
    return (bytes(out), i) if with_consumed else bytes(out)
def read_info(p):
    with open(p,'rb') as f:
        h=f.read(64)
        assert h[:8]==b'\x15\x1e\x1c\x0d\x0d\x23\x21\x00'
        o=12; o=h.index(b'\0',o)+1; o=h.index(b'\0',o)+1
        size,csz,usz,flags=struct.unpack('>QIII',h[o:o+20])
        f.seek(4096); c=f.read(csz)
    bi, consumed=lz4_lenient(c, usz, with_consumed=True)
    q=16; n,=struct.unpack('>I',bi[q:q+4]); q+=4
    blocks=[]
    for _ in range(n):
        u,cc,fl=struct.unpack('>IIH',bi[q:q+10]); q+=10; blocks.append((u,cc,fl))
    nn,=struct.unpack('>I',bi[q:q+4]); q+=4; nodes=[]
    for _ in range(nn):
        off,sz,fl=struct.unpack('>QQI',bi[q:q+20]); q+=20
        e=bi.index(b'\0',q); nodes.append((off,sz,fl,bi[q:e].decode('latin1'))); q=e+1
    return dict(flags=flags,csz=csz,usz=usz,blocks=blocks,nodes=nodes,bi_len=len(bi),q=q,info_consumed=consumed)
import os, re, zipfile, numpy as np

GAME = os.environ.get("NARAKA_STREAMING_ASSETS", "NARAKA_STREAMING_ASSETS")

def decompress_block(data, size, flags):
    kind = flags & 0x3f
    if kind == 0:
        result = data
    elif kind == 6:
        result = lz4.block.decompress(data, uncompressed_size=size)
    elif kind == 8:
        vendor = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'archive', '3d-viewer', 'viewer', 'resources', 'vendor', 'python')
        if vendor not in sys.path: sys.path.insert(0, vendor)
        import zstandard
        result = zstandard.ZstdDecompressor().decompress(data, max_output_size=size)
    else:
        raise ValueError(f'Unsupported Naraka block codec {kind}')
    if len(result) != size:
        raise ValueError(f'Block size mismatch: {len(result)} != {size}')
    return result


def unpack(p, outdir):
    """Container: custom 8-byte magic, UnityFS v7 header, LZ4 block table at 0x1000,
    data blocks LZ4 (compression id 6) each aligned to 4 KB. No encryption."""
    info = read_info(p); f = open(p, 'rb'); os.makedirs(outdir, exist_ok=True)
    nodes = info['nodes']; outs = [open(os.path.join(outdir, n[3]), 'wb') for n in nodes]
    pos = (4096 + info['info_consumed'] + 4095) // 4096 * 4096; ustart = 0
    for u, c, fl in info['blocks']:
        f.seek(pos); d = f.read(c)
        data = decompress_block(d, u, fl)
        for (off, sz, _, _), o in zip(nodes, outs):
            a = max(off, ustart); b = min(off + sz, ustart + len(data))
            if a < b: o.write(data[a - ustart:b - ustart])
        ustart += len(data); pos = (pos + c + 4095) // 4096 * 4096
    for o in outs: o.close()
    return [n[3] for n in nodes]

def find(pattern):
    d = zipfile.ZipFile(os.path.join(GAME, 'AppRes.info')).read('data')
    bre = re.compile(rb'(?:[0-9a-z_]+/)*[0-9a-f]/[0-9a-z]/[0-9a-f]{16}|[0-9a-f]{16}/[0-9a-f]{16}(?:/[0-9a-f]{16})?')
    from source_catalog import asset_entries
    tok = sorted([(m.start(), 'B', m.group().decode()) for m in bre.finditer(d)] +
                 [(offset, 'A', path) for offset, path in asset_entries(d)])
    cur = None; rx = re.compile(pattern, re.I)
    for _, k, s in tok:
        if k == 'B': cur = s
        elif rx.search(s): print(f"{cur}\t{s}")   # bundle (approximate) <TAB> original asset path

FMT = {0:('f',4),1:('e',2),2:('B',1),3:('b',1),4:('H',2),5:('h',2),6:('B',1),7:('b',1),8:('H',2),9:('h',2),10:('I',4),11:('i',4)}
def mesh_obj(tt):
    vd = tt['m_VertexData']; n = vd['m_VertexCount']; buf = bytes(vd['m_DataSize']); ch = vd['m_Channels']
    streams = {}
    for c in ch:
        if c['dimension']: streams.setdefault(c['stream'], []).append(c)
    stride = {s: max(c['offset'] + FMT[c['format']][1] * c['dimension'] for c in cs) for s, cs in streams.items()}
    base = {}; off = 0
    for s in sorted(stride): base[s] = off; off = (off + stride[s] * n + 15) // 16 * 16
    def get(i):
        c = ch[i]
        if not c['dimension']: return None
        code, sz = FMT[c['format']]
        a = np.frombuffer(buf, np.uint8, stride[c['stream']] * n, base[c['stream']]).reshape(n, stride[c['stream']])
        return a[:, c['offset']:c['offset'] + sz * c['dimension']].copy().view('<' + code).reshape(n, -1).astype(np.float32)
    pos, nrm, uv = get(0), get(1), get(4)
    w = 2 if tt['m_IndexFormat'] == 0 else 4
    idx = np.frombuffer(bytes(bytearray(tt['m_IndexBuffer'])), '<u2' if w == 2 else '<u4')
    L = [f"o {tt['m_Name']}"] + [f"v {-x} {y} {z}" for x, y, z in pos]
    if uv is not None: L += [f"vt {u} {v}" for u, v in uv]
    if nrm is not None: L += [f"vn {-x} {y} {z}" for x, y, z in nrm]
    for si, sm in enumerate(tt['m_SubMeshes']):
        L.append(f"g submesh{si}")
        s = sm['firstByte'] // w
        for a, b, c in idx[s:s + sm['indexCount']].reshape(-1, 3) + sm['baseVertex'] + 1:
            L.append(f"f {c}/{c}/{c} {b}/{b}/{b} {a}/{a}/{a}")
    return '\n'.join(L) + '\n'

def export(src, out):
    import UnityPy
    os.makedirs(out, exist_ok=True); env = UnityPy.load(src)
    for o in env.objects:
        t = o.type.name
        try:
            if t == 'Texture2D':
                tx = o.read(); tx.image.save(os.path.join(out, f"{tx.m_Name}.png"))
            elif t == 'Mesh':
                tt = o.read_typetree()
                open(os.path.join(out, f"{tt['m_Name']}_{o.path_id & 0xffffffff:08x}.obj"), 'w').write(mesh_obj(tt))
        except Exception as e:
            print('skip', t, o.path_id, e)

if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'find': find(sys.argv[2])
    elif cmd == 'unpack': print(unpack(sys.argv[2], sys.argv[3]))
    elif cmd == 'export': export(sys.argv[2], sys.argv[3])
