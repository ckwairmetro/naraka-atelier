"""Generalized cosmetic recipes. The rejected outfit route is disabled."""
import copy,gzip,hashlib,json,os,shutil,struct,threading,uuid,zipfile
from collections import defaultdict
from pathlib import Path
from core import Engine,HERE,COMMON,SHOW,EXTRA,LABELS,save_json,ensure_closed,sha_file,Trial
from native_edit import Session,CommonEditor
from table_codec import section_rows

ARCHIVE='e/5/e50ef81ba77ae51a'
OUTFIT_REGRESSION = (
    'Generalized outfit swaps are disabled: the 2026-11-14 battle-route trial '
    'reintroduced logout. The previously tested installed outfit profile is preserved.'
)
def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]

def hierarchy(cab,root):
    result=[];seen=set();pending=[root]
    while pending:
        pid=pending.pop()
        if pid in seen:continue
        seen.add(pid);obj=cab.sf.objects[pid];tree=cab.tree(pid);result.append((pid,obj.type.name,tree))
        for _,ptr in tree.get('m_Component',[]):
            if ptr['m_FileID']:raise ValueError('External prefab component pointer requires explicit resolution')
            component=ptr['m_PathID'];co=cab.sf.objects[component];ct=cab.tree(component);result.append((component,co.type.name,ct))
            if co.type.name in ('Transform','RectTransform'):
                for child in ct.get('m_Children',[]):
                    if child['m_FileID']:raise ValueError('External child Transform')
                    tr=cab.tree(child['m_PathID']);p=tr['m_GameObject']
                    if p['m_FileID']:raise ValueError('External child GameObject')
                    pending.append(p['m_PathID'])
    return result

class GeneralizedEngine(Engine):
    def __init__(self,*args,**kwargs):
        resources=Path(kwargs.get('resources') or HERE/'resources')
        with gzip.open(resources/'generalized.json.gz','rt',encoding='utf8') as f:self.general=json.load(f)
        self._contexts={};super().__init__(*args,**kwargs)

    def intrinsic(self,item):
        if item['c']=='outfit':
            return OUTFIT_REGRESSION
        return super().intrinsic(item)

    def compatible(self,src,tgt,hero=None):
        if src['c']==tgt['c']=='outfit':
            return OUTFIT_REGRESSION
        return super().compatible(src,tgt,hero)

    def recipes(self,s):
        target=self.items[s['target']]
        if target['c']=='outfit':raise ValueError(OUTFIT_REGRESSION)
        return super().recipes(s)

    def validate(self,selections):
        if not isinstance(selections,list) or len(selections)>100:raise ValueError('At most100 selections are supported')
        seen=set();jobs=[];model_sources=set()
        for s in selections:
            if not isinstance(s,dict) or set(s)-{'source','target','hero','options'}:raise ValueError('Unknown selection fields')
            if s.get('source') not in self.items or s.get('target') not in self.items:raise ValueError('Unknown catalogue selection')
            src,tgt=self.items[s['source']],self.items[s['target']]
            reason=self.compatible(src,tgt,s.get('hero'))
            if reason:raise ValueError(reason)
            if s['source'] in seen:raise ValueError('Duplicate source selection')
            seen.add(s['source']);model_sources.add(s['source'])
            if not isinstance(s.get('options',{}),dict):raise ValueError('Options must be an object')
            if tgt['c']=='outfit':
                variant=s.get('options',{}).get('variant',0)
                if not isinstance(variant,int) or not 0<=variant<len(self.general['outfits'][str(tgt['id'])]['temps']):raise ValueError('Outfit actor variant is invalid')
            else:jobs.extend(self.recipes(s))
        if model_sources & {s['target'] for s in selections}:raise ValueError('Cyclic or chained model swaps are not supported')
        writes={}
        for table,sec,a,b,fs in jobs:
            values=self.row(table,sec,b)
            for field in fs:
                key=(table,sec,a,field)
                if key in writes and writes[key]!=values[field]:raise ValueError('Conflicting shared native config fields')
                writes[key]=values[field]
        return jobs

    def _outfit(self,s,session,common,bindings,proof):
        # Forensic source is retained in work/quarantined-outfit-regression-2026-11-14.
        # Keep this final guard even if a caller bypasses selection validation.
        raise ValueError(OUTFIT_REGRESSION)

    def build(self,selections,progress=lambda s:None):
        self.validate(selections);self._contexts={}
        # Basic config edits and advanced edits share one common/index result.
        basic=[s for s in selections if self.items[s['target']]['c']!='outfit']
        layout,_=super().build(basic,progress);session=Session(self,layout);proof=[]
        try:
            common=CommonEditor(self,session.edit(COMMON).cab());bindings=BindingEditor(session)
            for s in selections:
                if self.items[s['target']]['c']=='outfit':
                    progress('Resolving complete outfit in the canonical source binding context')
                    self._outfit(s,session,common,bindings,proof)
            bindings.flush();common.flush();hashes=session.finish(progress)
            report={'passed':True,'selections':selections,'hashes':hashes,'advanced':proof,'native_rows':common.proof,'bundles':session.proofs,'native_tested':False,'base_files':session.base_refs,'before':session.before}
            save_json(layout/'validation.json',report);return layout,hashes
        except Exception:
            for b in session.editors.values():b.close()
            raise

    def apply(self,selections,progress=lambda s:None,features=None):
        # Reject the known failed recipe before any candidate or journal writes.
        self.validate(selections)
        requested=self.resolve_features(features) if hasattr(self,'resolve_features') else {}
        if not hasattr(self,'resolve_features') and features:raise ValueError('This compiler does not support feature settings')
        if not self.mutex.acquire(blocking=False):raise ValueError('Another operation is running')
        lock=self.state/'operation.lock';handle=None
        try:
            self._active_features=requested
            handle=lock.open('x');ensure_closed();status=self.check_build(strict=True)
            if not status['ok']:raise ValueError('; '.join(status['errors']))
            # Candidate construction may copy multi-gigabyte body bundles. Fail
            # before starting if there is no staging/rollback space.
            if any(shutil.disk_usage(p).free<8_000_000_000 for p in (self.state,self.game)):raise ValueError('At least8 GB of free space is needed for full native body staging/backups')
            layout,hashes=self.build(selections,progress);report=json.loads((layout/'validation.json').read_text(encoding='utf8'))
            if requested and report.get('features')!=requested:raise ValueError('Candidate does not contain the requested appearance features')
            status=self.check_build(strict=True)
            if not status['ok']:raise ValueError('; '.join(status['errors']))
            original={p:self.disk['expected'].get(p,report['before'][p]) for p in hashes}
            for p,h in original.items():
                if sha_file(self.game/p)!=h:raise ValueError('A resource changed during the build: '+p)
            transaction=self.state/'transactions'/layout.name
            changed={p:hashes[p] for p in hashes if original[p]!=hashes[p]}
            if changed and 'AppRes.info' not in changed:changed['AppRes.info']=hashes['AppRes.info']
            selected_original={p:original[p] for p in changed}
            pending={'candidate':str(layout),'transaction':str(transaction),'originals':selected_original,'candidates':changed,'old_profile':self.disk,'new_selections':selections,'new_features':requested}
            save_json(self.state/'pending.json',pending);self.pending=pending
            progress('Saving verified backups and applying; resource index is last')
            if changed:
                trial=Trial(self.game,layout,transaction,selected_original,changed)
                trial.progress=lambda phase,n,total,name:progress({'phase':phase,'percent':(78 if phase=='backup' else 88)+(10 if phase=='backup' else 9)*n/total,'message':('Verifying backup ' if phase=='backup' else 'Installing ')+name})
                result=trial.apply()
            else:result={'transaction':{'backup_id':None}}
            progress({'phase':'commit','percent':98,'message':'Committing verified profile'})
            expected=dict(self.disk['expected']);expected.update(hashes)
            profile={'selections':selections,'features':requested,'expected':expected,'generation':layout.name,'last_transaction':str(transaction),'owned_files':[p for p in hashes if p!='AppRes.info'],'base_files':report['base_files']}
            save_json(self.state/'profile.json',profile);self.disk=profile;(self.state/'pending.json').unlink();self.pending=None
            return {'applied':len(selections),'generation':layout.name,'backup':result['transaction']['backup_id'],'files':len(changed),'written_files':list(changed),'unchanged_files':len(hashes)-len(changed),'reused_bundles':sum(bool(p.get('reused_verified_candidate')) for p in report.get('bundles',{}).values())}
        finally:
            self.__dict__.pop('_active_features',None)
            if handle:handle.close();lock.unlink(missing_ok=True)
            self.mutex.release()

class BindingEditor:
    def __init__(self,session):self.session=session;self.loaded=False;self.aliases={}
    def load(self):
        if self.loaded:return
        from proto_codec import fields,row_key
        self.fields=fields;self.row_key=row_key
        path='assets/raw_resources/proto_bytes/custom_tags_data_archive.bytes'
        _,self.cab,entry=self.session.asset(path);self.pid=entry['asset']['m_PathID'];self.tree=self.cab.tree(self.pid)
        self.raw=self.tree['m_Script'].encode('utf8',errors='surrogateescape');self.top=fields(self.raw)
        self.rows={row_key(f['value']):f['value'] for f in self.top if f['number']==1};self.loaded=True
    def alias(self,original,context):
        self.load();source={k:v for k,v in self.rows.items() if k.startswith(original+'/')}
        if not source and original.endswith('_ui'):source={k:v for k,v in self.rows.items() if k.startswith(original[:-3]+'/')};original=original[:-3]
        if not source:raise ValueError('No native binding context for '+original)
        from proto_codec import delimited
        for k,row in source.items():
            key=context+k[len(original):]
            new=b''.join(delimited(1,key.encode()) if f['number']==1 else f['raw'] for f in self.fields(row))
            if key in self.aliases and self.aliases[key]!=new:raise ValueError('Conflicting private binding contexts')
            self.aliases[key]=new
    def flush(self):
        if not self.loaded:return
        from proto_codec import delimited
        if set(self.aliases)&set(self.rows):raise ValueError('Private binding context already exists in the base profile')
        data=self.raw+b''.join(delimited(1,self.aliases[k]) for k in sorted(self.aliases))
        after={self.row_key(f['value']):f['value'] for f in self.fields(data) if f['number']==1}
        if len(after)!=len(self.rows)+len(self.aliases) or any(after[k]!=v for k,v in self.rows.items()):raise ValueError('Native binding archive preservation failed')
        self.tree['m_Script']=data.decode('utf8',errors='surrogateescape');self.cab.put(self.pid,self.tree)
