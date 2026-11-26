"""File-backed Unity CAB edits and bounded-memory Naraka container packing.

Never reads a body/texture bundle into one giant bytes object. Original blocks
are indexed during extraction and reused when new logical blocks are identical.
"""
import copy,hashlib,json,os,shutil,struct,zlib
from pathlib import Path
import lz4.block
from UnityPy.files import SerializedFile
from UnityPy.streams import EndianBinaryReader
from UnityPy.helpers.TypeTreeHelper import read_typetree
from naraka_extract import read_info,decompress_block
from body_alias_trial import sha_file

BLOCK=131072
def digest_file(p,algorithm='sha256'):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,algorithm).hexdigest()

def proof_digest(value):
    # JSON turns numeric object IDs into string keys. Normalize before sorting
    # so a saved proof has the same checksum when it is read back.
    canonical=json.dumps(json.loads(json.dumps(value)),sort_keys=True,separators=(',',':'))
    return hashlib.sha256(canonical.encode()).hexdigest()

class CabEditor:
    def __init__(self,path):
        self.path=Path(path);self.handle=self.path.open('rb')
        self.sf=SerializedFile(EndianBinaryReader(self.handle),name=self.path.name)
        if self.sf.header.version!=21 or self.sf.header.endian!='<':raise ValueError('Unreviewed CAB format')
        if self.sf.header.file_size!=self.path.stat().st_size:raise ValueError('CAB node/file size mismatch')
        self.payloads={};self.trees={};self.opaque_tails={}
        self.abobj=next((o for o in self.sf.objects.values() if o.type.name=='AssetBundle'),None)
    def close(self):self.handle.close()
    def tree(self,pid):
        if pid not in self.trees:
            obj=self.sf.objects[pid]
            try:self.trees[pid]=obj.read_typetree()
            except ValueError:
                # Some native components append fields beyond the shipped
                # Unity type tree. Accept only a byte-exact parsed prefix;
                # retain the entire unknown suffix and prohibit resizing it.
                if obj.type.name!='MonoBehaviour':raise
                tree=obj.read_typetree(check_read=False);prefix=obj.save_typetree(tree);raw=obj.get_raw_data()
                if not prefix or len(prefix)>=len(raw) or not raw.startswith(prefix):raise ValueError('Native component prefix is not losslessly described')
                self.opaque_tails[pid]=(len(prefix),raw[len(prefix):]);self.trees[pid]=tree
        return copy.deepcopy(self.trees[pid])
    def put(self,pid,tree):
        obj=self.sf.objects[pid];raw=obj.save_typetree(tree)
        decoded=read_typetree(obj.serialized_type.node,EndianBinaryReader(raw,endian='<'),byte_size=len(raw),assetsfile=self.sf)
        if decoded!=tree:raise ValueError('Typed CAB serialization changed a value')
        if pid in self.opaque_tails:
            size,tail=self.opaque_tails[pid]
            if len(raw)!=size:raise ValueError('Cannot resize a native component with opaque trailing fields')
            raw+=tail
        self.payloads[pid]=raw;self.trees[pid]=copy.deepcopy(tree)
        if self.abobj and pid==self.abobj.path_id:self._container_cache=None
    def _container(self):
        if not self.abobj:return {}
        if getattr(self,'_container_cache',None) is None:
            if self.abobj.path_id not in self.trees:self.tree(self.abobj.path_id)
            self._container_cache=dict(self.trees[self.abobj.path_id]['m_Container'])
        return self._container_cache
    def entries(self):return copy.deepcopy(self._container())
    def entry(self,path):return copy.deepcopy(self._container().get(path))
    def alias(self,path,target):
        if self.abobj is None:raise ValueError('No AssetBundle lookup object')
        ab=self.tree(self.abobj.path_id);entries=dict(ab['m_Container'])
        if path in entries and entries[path]!=target:raise ValueError('Conflicting private prefab aliases')
        if path not in entries:
            ab['m_Container'].append((path,copy.deepcopy(target)));self.put(self.abobj.path_id,ab)
    def write(self,out):
        out=Path(out)
        if not self.payloads:return self.path,{'objects':[],'unchanged':True}
        out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(self.path,out)
        h=self.sf.header;self.handle.seek(0);metadata=self.handle.read(h.data_offset)
        edited=[]
        with out.open('r+b') as f:
            end=out.stat().st_size
            for pid,payload in self.payloads.items():
                obj=self.sf.objects[pid];old=obj.get_raw_data()
                if payload==old:continue
                needle=struct.pack('<qIIi',pid,obj.byte_start-h.data_offset,obj.byte_size,obj.type_id);at=metadata.find(needle,20)
                if at<0 or at%4 or metadata.find(needle,at+1)>=0:raise ValueError('Ambiguous native object directory')
                if len(payload)<=obj.byte_size:start=obj.byte_start
                else:start=(end+7)//8*8;end=start+len(payload)
                f.seek(start);f.write(payload);f.seek(at+8);f.write(struct.pack('<II',start-h.data_offset,len(payload)));edited.append(pid)
            # Integral-block growth allows texture sidecar blocks to be reused.
            size=self.path.stat().st_size+((max(0,end-self.path.stat().st_size)+BLOCK-1)//BLOCK)*BLOCK
            if size>=2**32:raise ValueError('CAB exceeds the reviewed 32-bit file-size range')
            f.seek(size-1);last=f.read(1)
            if not last:f.seek(size-1);f.write(b'\0')
            f.seek(4);f.write(struct.pack('>I',size));f.flush();os.fsync(f.fileno())
        with out.open('rb') as f:
            sf=SerializedFile(EndianBinaryReader(f),name=out.name)
            if set(sf.objects)!=set(self.sf.objects):raise ValueError('CAB object inventory changed')
            for pid,obj in self.sf.objects.items():
                expected=self.payloads.get(pid)
                old=obj.get_raw_data() if expected is None else expected
                new=sf.objects[pid]
                if new.get_raw_data()!=old or new.type_id!=obj.type_id:raise ValueError('Unexpected CAB payload/type change')
                if pid not in self.payloads and (new.byte_start,new.byte_size)!=(obj.byte_start,obj.byte_size):raise ValueError('Unchanged CAB object relocated')
        return out,{'objects':edited,'all_other_payloads_identical':True,'old_size':self.path.stat().st_size,'size':size,
                    'native_component_suffixes_preserved':{str(pid):len(self.opaque_tails[pid][1]) for pid in edited if pid in self.opaque_tails}}

class BundleEditor:
    def __init__(self,source,cache):
        self.source=Path(source);self.sha=sha_file(self.source);self.info=read_info(str(self.source))
        self.cache=Path(cache)/self.sha;self.cache.mkdir(parents=True,exist_ok=True);self.cabs={}
        nodes=self.info['nodes'];cursor=0
        for off,size,_,name in nodes:
            if off!=cursor or Path(name).name!=name:raise ValueError('Noncontiguous or unsafe bundle node layout')
            cursor+=size
        if cursor!=sum(b[0] for b in self.info['blocks']):raise ValueError('Unindexed bundle tail')
        marker=self.cache/'decoded.json'
        if marker.exists():
            m=json.loads(marker.read_text());self.block_index={tuple(x['key']):tuple(x['value']) for x in m['blocks']}
            for _,size,_,name in nodes:
                p=self.cache/name
                if not p.is_file() or p.stat().st_size!=size or sha_file(p)!=m['nodes'][name]:raise ValueError('Decoded cache integrity failure')
        else:
            handles=[(self.cache/n[3]).open('wb') for n in nodes];self.block_index={}
            pos=(4096+self.info['info_consumed']+4095)//4096*4096;logical=0
            try:
                with self.source.open('rb') as f:
                    for usize,csize,codec in self.info['blocks']:
                        f.seek(pos);raw=f.read(csize);data=decompress_block(raw,usize,codec)
                        self.block_index[(usize,hashlib.sha256(data).hexdigest())]=(pos,csize,codec)
                        for (off,size,_,_),out in zip(nodes,handles):
                            a,b=max(off,logical),min(off+size,logical+usize)
                            if a<b:out.write(data[a-logical:b-logical])
                        logical+=usize;pos=(pos+csize+4095)//4096*4096
            finally:
                for f in handles:f.close()
            record={'blocks':[{'key':list(k),'value':list(v)} for k,v in self.block_index.items()],'nodes':{n[3]:sha_file(self.cache/n[3]) for n in nodes}}
            temp=marker.with_suffix('.tmp');temp.write_text(json.dumps(record),encoding='utf8');os.replace(temp,marker)
    def cab(self,name=None):
        candidates=[n[3] for n in self.info['nodes'] if not n[3].lower().endswith(('.ress','.resource'))]
        if name:name=next((n for n in candidates if n.lower()==name.lower()),None)
        else:name=candidates[0]
        if not name:raise ValueError('CAB node was not found')
        if name not in self.cabs:self.cabs[name]=CabEditor(self.cache/name)
        return self.cabs[name]
    def asset(self,path):
        hits=[]
        for node in self.info['nodes']:
            if node[3].lower().endswith(('.ress','.resource')):continue
            cab=self.cab(node[3]);entry=cab.entry(path)
            if entry:
                if entry['asset']['m_FileID']:raise ValueError('Cross-CAB asset root needs an external pointer resolver')
                hits.append((cab,entry))
        if len(hits)!=1:raise ValueError('Asset root absent or ambiguous: '+path)
        return hits[0]
    def pack(self,out,work):
        signature=hashlib.sha256(b'atelier-pack-cache-v1'+self.sha.encode())
        for name,c in sorted(self.cabs.items()):
            for pid,payload in sorted(c.payloads.items()):
                if payload==c.sf.objects[pid].get_raw_data():continue
                signature.update(json.dumps([name,pid,hashlib.sha256(payload).hexdigest()]).encode())
        folder=self.cache.parent/'packed'/signature.hexdigest();record=folder/'proof.json';artifact=folder/'bundle'
        out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
        if out.resolve()==self.source.resolve() and not out.resolve().is_relative_to((self.cache.parent.parent/'generations').resolve()):
            raise ValueError('Cannot pack over the preserved source')
        if record.exists():
            proof=json.loads(record.read_text())
            checksum=proof.pop('_proof_digest',None)
            actual=proof_digest(proof)
            if checksum is not None and checksum!=actual:raise ValueError('Packed cache metadata changed; refusing reuse')
            if checksum is not None:
                if not artifact.exists() or sha_file(artifact)!=proof['sha256']:raise ValueError('Packed cache identity changed; refusing reuse')
                if out.exists():out.unlink()
                try:os.link(artifact,out)
                except OSError:shutil.copyfile(artifact,out)
                return dict(proof,reused_verified_candidate=True)
        proof=self._pack_uncached(out,work);folder.mkdir(parents=True,exist_ok=True)
        if not artifact.exists():
            try:os.link(out,artifact)
            except OSError:shutil.copyfile(out,artifact)
        if sha_file(artifact)!=proof['sha256']:raise ValueError('Packed cache verification failed')
        checksum=proof_digest(proof)
        temp=record.with_suffix('.tmp');temp.write_text(json.dumps(dict(proof,_proof_digest=checksum)));os.replace(temp,record)
        return dict(proof,reused_verified_candidate=False)

    def _pack_uncached(self,out,work):
        out=Path(out);out.parent.mkdir(parents=True,exist_ok=True);work=Path(work);work.mkdir(parents=True,exist_ok=True)
        changed=any(payload!=c.sf.objects[pid].get_raw_data() for c in self.cabs.values() for pid,payload in c.payloads.items())
        if not changed:
            if out.resolve()!=self.source.resolve():shutil.copyfile(self.source,out)
            return {'unchanged':True,'sha256':self.sha,'md5':digest_file(out,'md5'),'size':out.stat().st_size,'node_streams_verified':True,'objects':{}}
        paths=[];nodes=[];cursor=0;proof={}
        for _,size,flags,name in self.info['nodes']:
            if name in self.cabs:
                p,detail=self.cabs[name].write(work/name);proof[name]=detail
            else:p=self.cache/name
            size=p.stat().st_size;nodes.append((cursor,size,flags,name));cursor+=size;paths.append(p)
        with self.source.open('rb') as f:header=bytearray(f.read(4096))
        field=header.index(b'\0',header.index(b'\0',12)+1)+1
        oldsize,_,_,flags=struct.unpack_from('>QIII',header,field)
        if oldsize!=self.source.stat().st_size+30 or flags!=582:raise ValueError('Unreviewed custom bundle header')
        # Preserve the original block partitions. Texture groups include short
        # blocks, so imposing a new uniform grid would recompress most textures.
        insertions=[]
        for old,new in zip(self.info['nodes'],nodes):
            delta=new[1]-old[1]
            if delta<0:raise ValueError('Shrinking a node is not supported')
            if delta:insertions.append((old[0]+old[1],delta))
        schedule=[];offset=0;ii=0
        for usize,_,_ in self.info['blocks']:
            end=offset+usize;cursor=offset
            while ii<len(insertions) and insertions[ii][0]<=end:
                at,delta=insertions[ii]
                if at<cursor:raise ValueError('Invalid node growth position')
                if at>cursor:schedule.append(at-cursor)
                schedule.extend([BLOCK]*(delta//BLOCK))
                if delta%BLOCK:schedule.append(delta%BLOCK)
                cursor=at;ii+=1
            if end>cursor:schedule.append(end-cursor)
            offset=end
        if ii!=len(insertions) or sum(schedule)!=sum(n[1] for n in nodes):raise ValueError('Logical block schedule does not cover nodes')
        chunks=work/'blocks.bin';blocks=[];crc=0;reused=0;size=0
        sources=[p.open('rb') for p in paths];source_index=0
        def read_logical(n):
            nonlocal source_index
            result=bytearray()
            while len(result)<n:
                if source_index>=len(sources):raise ValueError('Truncated logical node stream')
                data=sources[source_index].read(n-len(result))
                if data:result.extend(data)
                else:source_index+=1
            return bytes(result)
        with chunks.open('wb') as packed,self.source.open('rb') as original:
            try:
                for length in schedule:
                    data=read_logical(length);crc=zlib.crc32(data,crc);key=(length,hashlib.sha256(data).hexdigest());old=self.block_index.get(key)
                    if old:
                        at,csize,codec=old;original.seek(at);compressed=original.read(csize);reused+=1
                    else:
                        compressed=lz4.block.compress(data,mode='high_compression',compression=12,store_size=False);codec=6
                        if len(compressed)>=length:compressed,codec=data,0
                    blocks.append((length,len(compressed),codec));packed.write(compressed);packed.write(bytes((-len(compressed))%4096));size+=(len(compressed)+4095)//4096*4096
            finally:
                for f in sources:f.close()
        metadata=bytearray(16)+struct.pack('>I',len(blocks))
        for block in blocks:metadata+=struct.pack('>IIH',*block)
        metadata+=struct.pack('>I',len(nodes))
        for off,n,fl,name in nodes:metadata+=struct.pack('>QQI',off,n,fl)+name.encode('latin1')+b'\0'
        metadata+=bytes((-len(metadata))%4096);compressed=lz4.block.compress(bytes(metadata),store_size=False)
        start=(4096+len(compressed)+2+4095)//4096*4096;total=start+size
        struct.pack_into('>QIII',header,field,total+30,len(compressed)+150,len(metadata)+130,flags)
        with out.open('wb') as f,chunks.open('rb') as c:
            f.write(header);f.write(compressed);f.write(bytes(start-f.tell()));shutil.copyfileobj(c,f,1024*1024)
        check=read_info(str(out))
        if check['nodes']!=nodes or check['blocks']!=blocks or out.stat().st_size!=total:raise ValueError('Packed header/directory roundtrip failed')
        # Independently read the emitted compressed blocks, including CRC and
        # exact node streams, instead of trusting the packer's buffer accounting.
        at=(4096+check['info_consumed']+4095)//4096*4096;actual=0;node_index=0;pos=0
        handles=[p.open('rb') for p in paths]
        try:
            with out.open('rb') as f:
                for us,cs,co in check['blocks']:
                    f.seek(at);data=decompress_block(f.read(cs),us,co);actual=zlib.crc32(data,actual);offset=0
                    while offset<len(data):
                        remain=nodes[node_index][1]-pos;take=min(remain,len(data)-offset)
                        if handles[node_index].read(take)!=data[offset:offset+take]:raise ValueError('Packed node stream differs')
                        pos+=take;offset+=take
                        if pos==nodes[node_index][1]:node_index+=1;pos=0
                    at=(at+cs+4095)//4096*4096
        finally:
            for f in handles:f.close()
        if actual!=crc or node_index!=len(nodes):raise ValueError('Packed CRC/node verification failed')
        return {'crc':crc,'sha256':sha_file(out),'md5':digest_file(out,'md5'),'size':total,'blocks_reused':reused,'blocks':len(blocks),'objects':proof,'node_streams_verified':True}
    def close(self):
        for c in self.cabs.values():c.close()
