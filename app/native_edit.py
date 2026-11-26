"""Typed native table edits and a multi-bundle candidate session."""
import copy,hashlib,json,os,shutil,struct,zipfile
from pathlib import Path
from bundle_editor import BundleEditor,digest_file
from body_alias_trial import sha_file
from table_codec import RowDecoder,load_table,finish_table,section_rows,rebuild_table
from decode_appres import decode,encode

class RowEncoder:
    def __init__(self,decoder):self.decoder=decoder;self.schema=decoder.schema;self.cur={}
    def value(self,t,v,path):
        if t.endswith('[]'):
            if v is None:return b'\0'
            fixed=self.cur.get(path,'c');out=b'\1'
            if fixed=='c':out+=struct.pack('<i',len(v))
            elif len(v)!=fixed:raise ValueError('Native fixed array length changed: '+path)
            return out+b''.join(self.value(t[:-2],x,path+'/[]') for x in v)
        if t=='string':
            raw=v.encode('utf-16le',errors='surrogatepass');return struct.pack('<i',len(raw)//2)+raw
        prim={'int':'<i','float':'<f','short':'<h','long':'<q','bool':'<?'}
        if t in prim:return struct.pack(prim[t],v)
        if v is None:return b'\0'
        return b'\1'+self.obj(t.split('.')[-1],v,path)
    def obj(self,cls,v,path=''):
        return b''.join(self.value(t,v[k],path+'.'+k if path else k) for k,t in self.schema[cls])
    def row(self,section,value):
        self.cur=self.decoder.specs.get(section,{});raw=self.obj(section,value)
        self.decoder.row(section,raw) # complete typed readback, including fixed arrays
        return raw

class CommonEditor:
    def __init__(self,engine,cab):
        self.engine=engine;self.cab=cab;self.tables={};self.decoder=RowDecoder(engine.schema,engine.decoder.specs);self.encoder=RowEncoder(self.decoder);self.proof=[]
        self.new_ids={};self._section_cache={}
    def table(self,name):
        if name not in self.tables:
            pid=self.engine.pids[name];obj=self.cab.sf.objects[pid];tree=self.cab.tree(pid)
            from table_codec import ddbl_decode
            data=ddbl_decode(name,tree['m_Script'].encode('utf8',errors='surrogateescape'));self.tables[name]=[obj,tree,data]
        return self.tables[name]
    def section(self,table,section):
        # Reuse parsed offsets/raw immutable row bytes only while the exact
        # table byte object is unchanged. Mutation creates a new bytes object.
        data=self.table(table)[2]
        if not isinstance(data,bytes):
            self._section_cache.pop(table,None);return section_rows(data,section)
        cached=self._section_cache.get(table)
        if cached is None or cached[0] is not data:
            cached=(data,{});self._section_cache[table]=cached
        if section not in cached[1]:cached[1][section]=section_rows(data,section)
        return cached[1][section]
    def get(self,table,section,id):
        _,_,rows=self.section(table,section)
        # Decode anew so caller modifications cannot mutate a cached row.
        return self.decoder.row(section,rows[id])
    def alloc(self,table,section):
        key=(table,section)
        if key not in self.new_ids:
            starts={'BattleAction_Action':3699000,'ActorVisualStatusConfig_VisualStatusType':29900,'ActorVisualStatusConfig_VisualStatus':1999000}
            _,_,rows=self.section(table,section)
            first=max(rows)+1 if section in ('HeroVoice_TriggerEvtMap','RareSkin_RareSkin') else starts.get(section,90_000_000)
            self.new_ids[key]=[first,set(rows)]
        value,used=self.new_ids[key]
        while value in used:value+=1
        limit={'BattleAction_Action':3699999,'ActorVisualStatusConfig_VisualStatusType':29999,'ActorVisualStatusConfig_VisualStatus':1999999}.get(section,2**31-1)
        if value>limit:raise ValueError('Reviewed local presentation ID range is exhausted: '+section)
        used.add(value);self.new_ids[key][0]=value+1;return value
    def patch(self,table,section,id,changes,template=None):
        obj,tree,data=self.table(table);sec,rs,rows=self.section(table,section)
        if id in rows:
            before=self.decoder.row(section,rows[id]);value=copy.deepcopy(before)
        else:
            if template is None:raise ValueError('A native prototype is required for an appended row')
            value=copy.deepcopy(self.engine.row(table,section,template));before=None;value['_ID']=id
        if not set(changes)<=set(value):raise ValueError('Unknown native row fields: '+str(set(changes)-set(value)))
        value.update(copy.deepcopy(changes));raw=self.encoder.row(section,value)
        if value['_ID']!=id:raise ValueError('Native row identity mismatch')
        if before is None:
            sec=dict(sec,count=sec['count']+1);rs=rs+[dict(rs[-1],id=id,offset=0,size=0)]
        new=rebuild_table(data,sec,rs,id,raw);self.tables[table][2]=new
        _,_,check=self.section(table,section)
        if check[id]!=raw:raise ValueError('Native table row readback mismatch')
        self.proof.append({'table':table,'section':section,'id':id,'added':before is None,'fields':list(changes),'prototype':template})
        return id
    def flush(self):
        for name,(obj,tree,data) in self.tables.items():
            payload=finish_table(obj,tree,name,data)
            # TextAsset string bytes, including surrogate-escaped protobuf data,
            # are serialized by UnityPy with a complete typed roundtrip.
            reread=copy.deepcopy(tree);self.cab.put(obj.path_id,reread)

class Session:
    def __init__(self,engine,layout):
        self.engine=engine;self.layout=Path(layout);self.editors={};self.proofs={};self.base_refs=copy.deepcopy(engine.disk.get('base_files',{}));self.before={}
        self.source_manifest=engine.read('source-manifest.json',{})
        with zipfile.ZipFile(self.layout/'AppRes.info') as z:
            raw=z.read('data');self.zi=copy.copy(z.getinfo('data'));self.comment=z.comment
        self.original_index_data=raw
        self.index=decode(raw);self.records={b['bundle_name']:b for b in self.index['bundles']}
        self.assets={a:b['bundle_name'] for b in self.index['bundles'] for a in b['assets']}
    def baseline(self,rel):
        if Path(rel).is_absolute() or '..' in Path(rel).parts:raise ValueError('Unsafe bundle path')
        packaged=self.engine.resources/'baseline'/rel
        if packaged.exists():
            expected=self.engine.manifest['initial_installed'].get(rel)
            if expected and sha_file(packaged)!=expected:raise ValueError('Packaged base bundle identity differs: '+rel)
            return packaged
        if rel in self.source_manifest:
            r=self.source_manifest[rel];p=Path(r['path'])
            if sha_file(p)!=r['sha256']:raise ValueError('Preserved bundle source changed')
            if digest_file(p,'md5')!=self.records[rel]['file_hash']:raise ValueError('Preserved source belongs to a different base build/profile: '+rel)
            self.base_refs[rel]=r;return p
        source=self.engine.game/rel;record=self.records[rel]
        if digest_file(source,'md5')!=record['file_hash']:raise ValueError('Untracked/updated bundle cannot be adopted: '+rel)
        digest=sha_file(source);p=self.engine.state/'sources'/(digest+'.bundle');p.parent.mkdir(parents=True,exist_ok=True)
        if not p.exists():
            temp=p.with_suffix('.tmp');shutil.copyfile(source,temp)
            if sha_file(temp)!=digest:raise ValueError('Bundle changed during source snapshot')
            os.replace(temp,p)
        r={'path':str(p),'sha256':digest};self.source_manifest[rel]=r;self.base_refs[rel]=r
        from core import save_json
        save_json(self.engine.state/'source-manifest.json',self.source_manifest)
        return p
    def edit(self,rel):
        if rel not in self.editors:
            source=self.layout/rel if rel=='f/a/fab72152d7112058' else self.baseline(rel)
            # Record what is actually installed before this candidate; new
            # bundles are bound to the verified immutable base snapshot.
            verified_base=self.baseline(rel) if rel=='f/a/fab72152d7112058' else source
            self.before[rel]=(self.engine.disk['expected'][rel] if rel in self.engine.disk['expected'] else sha_file(verified_base))
            self.editors[rel]=BundleEditor(source,self.engine.state/'decoded-cache')
        return self.editors[rel]
    def alias(self,path,bundle):
        old=self.assets.get(path)
        if old and old!=bundle:raise ValueError('Private asset path ownership collision')
        if not old:self.records[bundle]['assets'].append(path);self.assets[path]=bundle
    def asset(self,path):
        if path not in self.assets:raise ValueError('Asset is not in the installed build: '+path)
        bundle=self.assets[path];cab,entry=self.edit(bundle).asset(path);return bundle,cab,entry
    def finish(self,progress=lambda s:None):
        hashes={};all_files=set(self.engine.disk.get('owned_files',[]))|set(self.editors)|{'f/a/fab72152d7112058','AppRes.info'}
        try:
            for n,(rel,b) in enumerate(self.editors.items(),1):
                progress(f'Packing and verifying {n}/{len(self.editors)} · '+rel)
                detail=b.pack(self.layout/rel,self.layout/'packing'/Path(rel).name)
                if not detail.get('unchanged'):self.records[rel].update(file_hash=detail['md5'],file_size=detail['size'],crc=detail['crc'])
                hashes[rel]=detail['sha256'];self.proofs[rel]=detail
            # Removed selections restore every previously touched bundle to its
            # captured base, not merely the common/index pair.
            for rel in sorted(all_files-{'AppRes.info'}-set(hashes)):
                dest=self.layout/rel
                if not dest.exists():
                    source=self.baseline(rel);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
                hashes[rel]=sha_file(dest);self.before[rel]=(self.engine.disk['expected'][rel] if rel in self.engine.disk['expected'] else sha_file(self.baseline(rel)))
            raw=encode(self.index)
            def semantic(value):
                if isinstance(value,dict):return {k:semantic(v) for k,v in value.items() if k not in ('offset','consumed_bytes')}
                if isinstance(value,list):return [semantic(v) for v in value]
                return value
            decoded=decode(raw)
            if semantic(decoded)!=semantic(self.index) or encode(decoded)!=raw:raise ValueError('Multi-bundle index roundtrip failed')
            seen=set()
            for b in self.index['bundles']:
                for asset in b['assets']:
                    if asset in seen:raise ValueError('Asset has more than one bundle owner')
                    seen.add(asset)
            if raw!=self.original_index_data:
                with zipfile.ZipFile(self.layout/'AppRes.info','w') as z:z.comment=self.comment;z.writestr(self.zi,raw)
            # A deterministic file order commits the index last.
            ordered={p:hashes[p] for p in sorted(hashes)};ordered['AppRes.info']=sha_file(self.layout/'AppRes.info')
            self.before['AppRes.info']=self.engine.disk['expected']['AppRes.info']
            return ordered
        finally:
            for b in self.editors.values():b.close()
