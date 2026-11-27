"""Catalogue, compatibility rules and reproducible resource-only profile compiler."""
import base64,copy,gzip,hashlib,json,os,re,shutil,sys,threading,time,uuid,zipfile
from collections import Counter,defaultdict
from pathlib import Path

HERE=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
sys.path.insert(0,str(HERE/'vendor'))
from body_alias_trial import Trial,sha_file,ensure_closed
from decode_appres import decode,encode
from build_body_alias_candidate import unpack_logical,load_sf
from pack_preserving_blocks import pack_preserving
from preserve_serialized_layout import replace_objects
from table_codec import RowDecoder,field_spans,load_table,finish_table,section_rows,rebuild_table,changed_rows

COMMON='f/a/fab72152d7112058'
LABELS={'outfit':'时装 · Outfits','hair':'发型 · Hair','accessory':'饰品 · Accessories','grapple':'飞索 · Grapples','weapon':'武器 · Weapons','background':'背景 · Backgrounds','pose':'姿势 · Poses','platform':'底座 · Pedestals','broadcast':'击败播报 · Broadcast','lootpile':'落物堆 · Loot pile','rescue':'救援 · Rescue','skill':'技能奥义 · Skill looks','effect':'效果定制 · Battle effects','voice':'语音 · Voice','music':'战斗音乐 · Music'}
W_FIELDS={'_Quality','_PresentationPrefabPath','_AppearFXID','_UIWeaponMappingIDs','_WeaponCustomDatas','_StagePrefabPath','_CutsceneName','_BGMName','_AudioEventName','_AudioEventNameNoMA','_CanCustomSkinEffect','_SkinEffectIDs','_CameraPosName','_CanUseCopyEffect','_HeroShowWeaponDefaultIdleState','_CustomFuncSetting','_CanUseFreeLookCam','_NeedPrePareAnim','_IconPath','_LargeIconPath'}
SHOW={'background':'BackGround','pose':'ShowAction','platform':'PlatformItem'}
EXTRA={'broadcast':('KillBroadcast','KillBroadcast_Skin',{'_PrefabPath','_InBattleAnim','_OutBattleAnim','_Icon'}),'lootpile':('InteractiveBuildSkin','InteractiveBuildSkin_InteractiveBuildSkin',{'_UIPrefabPath','_NeedReplacePath','_AudioEventName','_GoldenVoiceTriggerID','_GoldenVoiceOutGameEvtList','_PurpleVoiceTriggerID','_PurpleVoiceOutGameEvtLIst','_Icon'}),'rescue':('RescueSkin','RescueSkin_RescueSkin',{'_SkinId','_UISkinStateName','_SoulGraveFX','_ChainPrefab','_ChainType','_Icon'})}

def save_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');os.replace(tmp,path)

def import_catalogue(archive,dest,expected_version):
    """Parse data.js as JSON; never execute archive-provided HTML/JavaScript."""
    archive=Path(archive);digest=sha_file(archive);target=Path(dest)/digest
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist()
        if len(infos)>40000 or sum(i.file_size for i in infos)>600_000_000:raise ValueError('Catalogue archive exceeds limits')
        names=[i.filename for i in infos]
        if len(names)!=len(set(names)):raise ValueError('Duplicate catalogue archive entries')
        for i in infos:
            p=Path(i.filename)
            if i.filename.startswith('/') or p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename:raise ValueError('Unsafe ZIP path')
        source=z.read('naraka-catalogue/data.js').decode('utf8').strip()
        prefix='window.CATALOG = '
        if not source.startswith(prefix) or not source.endswith(';'):raise ValueError('Unsupported catalogue export format')
        data=json.loads(source[len(prefix):-1])
        if data.get('gameVersion',{}).get('clientVersion')!=expected_version:raise ValueError('Catalogue/client build mismatch: import refused')
        if not isinstance(data.get('items'),list) or not data.get('heroes'):raise ValueError('Catalogue is incomplete')
        if not (target/'catalogue.json').exists():
            staging=Path(dest)/(digest+'.'+uuid.uuid4().hex);staging.mkdir(parents=True)
            try:
                for i in infos:
                    if i.filename.startswith('naraka-catalogue/icons/') and not i.is_dir():
                        p=staging/'icons'/Path(i.filename).name
                        if p.suffix.lower() not in ('.webp','.png','.jpg','.jpeg'):raise ValueError('Unsupported icon file')
                        if p.exists():raise ValueError('Colliding icon paths')
                        p.parent.mkdir(exist_ok=True);p.write_bytes(z.read(i))
                save_json(staging/'catalogue.json',data)
                if target.exists():shutil.rmtree(staging)
                else:os.replace(staging,target)
            except Exception:
                shutil.rmtree(staging,ignore_errors=True);raise
    return target,data,digest

class Engine:
    def __init__(self,state_dir=None,resources=None,*,game_dir=None):
        self.resources=Path(resources or HERE/'resources')
        self.state=Path(state_dir or Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Naraka Atelier')
        self.state.mkdir(parents=True,exist_ok=True)
        self.manifest=json.loads((self.resources/'build.json').read_text(encoding='utf8'))
        self.game=Path(game_dir if game_dir is not None else self.manifest['game'])
        self.schema=json.loads((self.resources/'schema.json').read_text(encoding='utf8'))
        self.decoder=RowDecoder(self.schema,json.loads((self.resources/'specs.json').read_text(encoding='utf8')))
        with gzip.open(self.resources/'native_rows.json.gz','rt',encoding='utf8') as f:n=json.load(f)
        self.pids=n['pids'];self.rows={t:{s:{int(k):base64.b64decode(v) for k,v in rs.items()} for s,rs in secs.items()} for t,secs in n['tables'].items()}
        self.native={};self.mutex=threading.Lock();self.job={'busy':False,'message':'Ready','error':None};self._hash_cache={}
        settings=self.read('settings.json',{});archive=Path(settings.get('catalogue',''))
        if not archive.is_file():archive=self.resources/'catalogue.zip'
        self.catalogue_dir,self.catalogue,self.catalogue_digest=import_catalogue(archive,self.state/'catalogues',self.manifest['catalogue_version'])
        self.load_items();self.disk=self.read('profile.json',{'selections':[],'expected':self.manifest['initial_installed'],'generation':None})
        # A pending journal is not silently accepted after a crash.
        self.pending=self.read('pending.json',None)
        idx=decode(zipfile.ZipFile(self.resources/'baseline/AppRes.info').read('data'))
        self.assets={a for b in idx['bundles'] for a in b['assets']};self.asset_stems={Path(a).stem.lower() for a in self.assets}
        self.cosmetic_keys=set(json.loads((self.resources/'cosmetic-keys.json').read_text(encoding='utf8')))
        self.coverage=self.audit()
        for rel in (COMMON,'AppRes.info'):
            if sha_file(self.resources/'baseline'/rel)!=self.manifest['initial_installed'][rel]:raise ValueError('Packaged base profile failed its integrity check')

    def read(self,name,default):
        p=self.state/name
        return json.loads(p.read_text(encoding='utf8')) if p.exists() else default

    def row(self,table,section,id):
        key=(table,section,int(id))
        if key not in self.native:self.native[key]=self.decoder.row(section,self.rows[table][section][int(id)])
        return self.native[key]

    def load_items(self):
        data=self.catalogue;items=copy.deepcopy(data['items'])
        # Folded upgrade records stay visible, but cannot inherit a native pass.
        for i in data.get('folded',[]):
            i=copy.deepcopy(i);i['_folded']=True;items.append(i)
        for category,ls in data.get('extra',{}).items():
            for i in ls:items.append(dict(i,c=category))
        for category,key in [('skill','skillFx'),('effect','battleFx'),('voice','voice'),('music','songs')]:
            records=data.get(key,[])
            if isinstance(records,dict):records=records.values()
            for i in records:
                i=dict(i,c=category)
                hero=i.get('hero')
                if category=='skill':hero=data.get('skills',{}).get(str(i.get('skill')),{}).get('hero')
                if hero:i['h']=[hero]
                items.append(i)
        self.items={}
        for i in items:
            key=str(i['c'])+':'+str(i['id'])
            if key in self.items:raise ValueError('Duplicate category/item identity: '+key)
            i['key']=key;self.items[key]=i

    def intrinsic(self,item):
        c=item['c'];id=int(item['id']) if str(item['id']).isdigit() else 0
        if item.get('_folded'):return 'Upgrade stage: requires a dedicated native route'
        if c=='outfit':return 'Whole-prefab/binding adapter is not generalized; current tested outfits remain installed'
        if c in ('skill','effect','voice','music'):return 'Native trigger/audio adapter not generalized; current tested effects are retained'
        if item.get('stub') or item.get('pending'):return 'Catalogue marks this resource unresolved'
        if c not in LABELS:return 'No adapter for this category'
        if c=='weapon':
            if any(item.get(k) for k in ('z','lv','fm')):return 'Numbered/upgrade/form item: requires a dedicated appearance-rule adapter'
            for sec in ('WeaponSkin_WeaponSkin','WeaponSkin_WeaponBattleSkin'):
                row=self.row('WeaponSkin',sec,id)
                for k in ('_PresentationPrefabPath','_DropWeaponPrefabPath','_IconPath','_WeaponIcon','_BattleItemIcon'):
                    value=row.get(k)
                    if value and Path(value).stem.lower() not in self.asset_stems:return 'Native asset unresolved: '+value
        elif c=='hair':
            hair=self.row('HairItem','HairItem_Hair',id)
            if len(hair['_HairConfigs'] or [])!=1:return 'Multi-visual hair requires a variant-specific recipe'
            if hair.get('_HairEffects') or item.get('hfx'):return 'Red-hair effect controller requires a dedicated recipe'
            visual=self.row('HairConfig','HairConfig_HairVisual',hair['_HairConfigs'][0])
            if visual['_CosmeticAsset'] not in self.cosmetic_keys:return 'Hair cosmetic archive key is unresolved'
        elif c in ('accessory','grapple'):
            itemrow=self.row('OrnamentItem','OrnamentItem_OrnamentItem',id)
            if itemrow.get('_ParentOrnamentId') or item.get('s') in (1012,1019,1099):return 'Doll, Mole Hook or linked variant is not supported by the ordinary ornament adapter'
            cfg=itemrow['_ExtraConfigID'];self.row('OrnamentConfig','OrnamentConfig_OrnamentConfig',cfg)
            cfgrow=self.row('OrnamentConfig','OrnamentConfig_OrnamentConfig',cfg)
            for k in ('_PrefabPath','_UIPrefabPath'):
                if cfgrow.get(k) and Path(cfgrow[k]).stem.lower() not in self.asset_stems:return 'Native ornament asset unresolved: '+cfgrow[k]
            if c=='grapple':self.row('OrnamentConfig','OrnamentConfig_ChainArrow',cfg)
        elif c in SHOW:
            row=self.row('ShowOffItemConfig','ShowOffItemConfig_'+SHOW[c],id)
            if c=='pose' and any(row.get(k) for k in ('_IsGroupAction','_CoupleOverrideList','_TrioOverrideList')):return 'Group/couple/trio pose needs partner-context handling'
            for k in ('_BackgroundPrefabPath','_PlatformPrefabPath','_Bg2DPath','_ItemIconPath'):
                if row.get(k) and Path(row[k]).stem.lower() not in self.asset_stems:return 'Showcase asset unresolved: '+row[k]
        elif c in EXTRA:
            t,s,_=EXTRA[c];self.row(t,s,id)
        return None

    def audit(self):
        counts=defaultdict(Counter)
        for i in self.items.values():
            try:reason=self.intrinsic(i)
            except (KeyError,ValueError,IndexError,TypeError) as e:reason='Native row/schema unresolved: '+str(e)[:100]
            i['support']={'available':not bool(reason),'reason':reason,'evidence':'Static adapter; pair needs native visual acceptance' if not reason else 'Not enabled'}
            counts[i['c']]['total']+=1;counts[i['c']]['available' if not reason else 'blocked']+=1
        report={c:dict(v) for c,v in counts.items()};save_json(self.state/'catalogue-coverage.json',report);return report

    def compatible(self,src,tgt,hero=None):
        if src['key']==tgt['key']:return 'Choose a different target'
        if src['c']!=tgt['c']:return 'Categories differ'
        if not src['support']['available']:return src['support']['reason']
        if not tgt['support']['available']:return tgt['support']['reason']
        c=src['c']
        if c=='weapon':
            if not src.get('w') or src.get('w')!=tgt.get('w'):return 'Weapon families differ'
            for section,field in [('WeaponSkin_WeaponSkin','_WeaponTypePresentation'),('WeaponSkin_WeaponBattleSkin','_WeaponItemType')]:
                if self.row('WeaponSkin',section,src['id'])[field]!=self.row('WeaponSkin',section,tgt['id'])[field]:return 'Native weapon classes differ'
            if int(src['id'])==2311500:return 'This source drives the installed Dragonsteed/Fengqiuhuang effect recipe; changing its model is blocked until that recipe can be rebuilt'
        elif c not in EXTRA:
            shared=set(src.get('h',[])) & set(tgt.get('h',[]))
            if hero is None or int(hero) not in shared:return 'Both items must support the selected hero'
            if c in ('accessory','grapple') and src.get('s')!=tgt.get('s'):return 'Attachment slots differ'
            if c=='hair':
                a=self.row('HairItem','HairItem_Hair',src['id']);b=self.row('HairItem','HairItem_Hair',tgt['id'])
                if (a['_SpecialColorGroup'],a['_HighlightDyeingFunctionLevels'])!=(b['_SpecialColorGroup'],b['_HighlightDyeingFunctionLevels']):return 'Hair dye/controller capabilities differ'
            if c in ('accessory','grapple'):
                a=self.row('OrnamentItem','OrnamentItem_OrnamentItem',src['id']);b=self.row('OrnamentItem','OrnamentItem_OrnamentItem',tgt['id'])
                ca=self.row('OrnamentConfig','OrnamentConfig_OrnamentConfig',a['_ExtraConfigID']);cb=self.row('OrnamentConfig','OrnamentConfig_OrnamentConfig',b['_ExtraConfigID'])
                if ca['_Type']!=cb['_Type']:return 'Native ornament loader types differ'
        return None

    def recipes(self,selection):
        src=self.items[selection['source']];tgt=self.items[selection['target']]
        reason=self.compatible(src,tgt,selection.get('hero'))
        if reason:raise ValueError(reason)
        c=src['c'];a=int(src['id']);b=int(tgt['id']);out=[]
        def add(t,s,a,b,fs):out.append((t,s,a,b,set(fs)))
        if c=='weapon':
            add('WeaponSkin','WeaponSkin_WeaponSkin',a,b,W_FIELDS)
            add('WeaponSkin','WeaponSkin_WeaponBattleSkin',a,b,{'_WeaponTempIDList','_DropWeaponPrefabPath','_ReplaceRangeAgentModelId','_WeaponCustomDatas','_WeaponIcon','_BattleItemIcon'})
        elif c=='hair':
            sa=self.row('HairItem','HairItem_Hair',a);ta=self.row('HairItem','HairItem_Hair',b)
            add('HairConfig','HairConfig_HairVisual',sa['_HairConfigs'][0],ta['_HairConfigs'][0],{'_CosmeticAsset','_HairIconPath','_IconPath'})
            add('HairItem','HairItem_Hair',a,b,{'_UIIconPath'})
        elif c in ('accessory','grapple'):
            sa=self.row('OrnamentItem','OrnamentItem_OrnamentItem',a);ta=self.row('OrnamentItem','OrnamentItem_OrnamentItem',b)
            ac,bc=sa['_ExtraConfigID'],ta['_ExtraConfigID'];native=self.row('OrnamentConfig','OrnamentConfig_OrnamentConfig',bc)
            add('OrnamentConfig','OrnamentConfig_OrnamentConfig',ac,bc,set(native)-{'_ID','_Type','_Description'})
            add('OrnamentItem','OrnamentItem_OrnamentItem',a,b,{'_Icon','_ReplaceHair','_FacePartReplace'})
            if c=='grapple':add('OrnamentConfig','OrnamentConfig_ChainArrow',ac,bc,set(self.row('OrnamentConfig','OrnamentConfig_ChainArrow',bc))-{'_ID'})
        elif c in SHOW:
            section='ShowOffItemConfig_'+SHOW[c];fields=self.row('ShowOffItemConfig',section,b)
            allowed={'background':{'_BackgroundPrefabPath','_Bg2DPath','_AlternativeBgList','_ItemIconPath'},'platform':{'_PlatformPrefabPath','_DeviceStateName','_ItemIconPath'},'pose':{'_StateName','_ItemIconPath','_UIWeaponID','_UIWeaponStateName','_UIWeaponDataID'}}[c]
            # Native background/platform field spellings differ by section.
            allowed|={k for k in fields if ('Prefab' in k or 'Icon' in k) and k not in {'_LinkageSkinBtnBgPath'}}
            add('ShowOffItemConfig',section,a,b,allowed & set(fields))
        elif c in EXTRA:
            t,s,fs=EXTRA[c];add(t,s,a,b,fs)
        return out

    def validate(self,selections):
        if not isinstance(selections,list) or len(selections)>100:raise ValueError('Profile must contain at most100 selections')
        seen=set();writes={};jobs=[]
        for s in selections:
            if not isinstance(s,dict) or set(s)-{'source','target','hero'}:raise ValueError('Unexpected selection fields')
            if s['source'] not in self.items or s['target'] not in self.items:raise ValueError('Item is absent from this catalogue')
            if s['source'] in seen:raise ValueError('A source may have only one target')
            seen.add(s['source'])
            for t,sec,a,b,fs in self.recipes(s):
                values=self.row(t,sec,b)
                for f in fs:
                    key=(t,sec,a,f)
                    if key in writes and writes[key]!=values[f]:raise ValueError('Selections conflict through shared native config')
                    writes[key]=values[f]
                jobs.append((t,sec,a,b,fs))
        # Chains/cycles can mutate the source identity behind another selection.
        targets={s['target'] for s in selections}
        if seen & targets:raise ValueError('Chained or cyclic swaps are not supported in one profile')
        return jobs

    def hash(self,path):
        st=path.stat();key=(str(path),st.st_size,st.st_mtime_ns)
        if key not in self._hash_cache:self._hash_cache[key]=sha_file(path)
        return self._hash_cache[key]

    def check_build(self,strict=False):
        errors=[];game_root=self.game.parent.parent
        # No version-label-only bypass: the installed build is hash-bound.
        for rel,h in self.manifest['critical'].items():
            p=game_root/rel
            if not p.is_file() or (sha_file(p) if strict else self.hash(p))!=h:errors.append('Client updated or file differs: '+rel)
        expected=self.disk['expected']
        for rel,h in expected.items():
            p=self.game/rel
            if not p.is_file() or (sha_file(p) if strict else self.hash(p))!=h:errors.append('Resource differs from the tracked profile: '+rel)
        if self.catalogue['gameVersion']['clientVersion']!=self.manifest['catalogue_version']:errors.append('Catalogue version does not match the verified client')
        if self.pending:errors.append('An interrupted operation needs recovery before applying another profile')
        return {'ok':not errors,'version':self.manifest['catalogue_version'],'catalogue_built':self.catalogue['built'],'errors':errors,'fingerprint_files':len(expected)+len(self.manifest['critical'])}

    def build(self,selections,progress=lambda s:None):
        jobs=self.validate(selections);progress('Reading the preserved base profile')
        decoder=RowDecoder(self.schema,self.decoder.specs)
        layout=self.state/'generations'/uuid.uuid4().hex;layout.mkdir(parents=True)
        baseline=self.resources/'baseline';data,info=unpack_logical(baseline/COMMON);sf=load_sf(data)
        changes={};proof=[]
        for t in dict.fromkeys(j[0] for j in jobs):
            obj,tree,original=load_table(sf,self.pids[t],t);current=original
            for _,sec,a,b,allowed in [j for j in jobs if j[0]==t]:
                s,rs,rm=section_rows(current,sec);source=rm[a];target=self.rows[t][sec][b]
                sa=field_spans(decoder,self.schema,sec,source);sb=field_spans(decoder,self.schema,sec,target)
                if not allowed<=set(sa) or not allowed<=set(sb):raise ValueError('Adapter fields do not match native schema')
                row=b''.join(target[sb[k][0]:sb[k][1]] if k in allowed else source[v[0]:v[1]] for k,v in sa.items())
                before=decoder.row(sec,source);after=decoder.row(sec,row);canonical=self.row(t,sec,b)
                delta={k for k in before if before[k]!=after[k]}
                if not delta<=allowed or after['_ID']!=a:raise ValueError('Field-level validation failed')
                for k in allowed:
                    if after[k]!=canonical[k]:raise ValueError('Target field readback differs')
                    # Icon references are checked against the native index.
                    if ('Icon' in k) and isinstance(after[k],str) and after[k] and after[k].lower() not in self.asset_stems:raise ValueError('Target icon is missing: '+after[k])
                    if k in {'_PrefabPath','_UIPrefabPath','_PresentationPrefabPath','_DropWeaponPrefabPath','_ArrowPrefabPath'} and isinstance(after[k],str) and after[k]:
                        stem=Path(after[k]).stem.lower()
                        if stem not in self.asset_stems:raise ValueError('Target prefab is unresolved: '+after[k])
                current=rebuild_table(current,s,rs,a,row);proof.append({'table':t,'section':sec,'source':a,'target':b,'fields':sorted(delta)})
            expected={(j[1],j[2]) for j in jobs if j[0]==t}
            if not set(changed_rows(original,current))<=expected:raise ValueError('An unrelated native table row changed')
            changes[obj.path_id]=finish_table(obj,tree,t,current)
        progress('Validating and packing the candidate')
        if changes:
            authored,_=replace_objects(data,changes);(layout/COMMON).parent.mkdir(parents=True)
            pack_preserving(baseline/COMMON,[(0,len(authored),*info['nodes'][0][2:])],authored,layout/COMMON)
            fresh=load_sf(authored)
            for pid in sf.objects:
                if pid not in changes and sf.objects[pid].get_raw_data()!=fresh.objects[pid].get_raw_data():raise ValueError('An unrelated serialized object changed')
            import zlib
            with zipfile.ZipFile(baseline/'AppRes.info') as z:raw=z.read('data');zi=copy.copy(z.getinfo('data'));comment=z.comment
            idx=decode(raw);new=copy.deepcopy(idx);record=next(b for b in new['bundles'] if b['bundle_name']==COMMON)
            record.update(file_hash=hashlib.md5((layout/COMMON).read_bytes()).hexdigest(),file_size=(layout/COMMON).stat().st_size,crc=zlib.crc32(authored))
            norm=copy.deepcopy(new)
            for a,b in zip(idx['bundles'],norm['bundles']):
                if a['bundle_name']==COMMON:
                    for k in ('file_hash','file_size','crc'):b[k]=a[k]
            if norm!=idx or decode(encode(new))!=new:raise ValueError('Index roundtrip or scope validation failed')
            with zipfile.ZipFile(layout/'AppRes.info','w') as z:z.comment=comment;z.writestr(zi,encode(new))
        else:
            for rel in (COMMON,'AppRes.info'):
                p=layout/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(baseline/rel,p)
        hashes={p:sha_file(layout/p) for p in (COMMON,'AppRes.info')}
        save_json(layout/'validation.json',{'passed':True,'selections':selections,'edits':proof,'hashes':hashes,'native_tested':False})
        return layout,hashes

    def apply(self,selections,progress=lambda s:None):
        if not self.mutex.acquire(blocking=False):raise ValueError('Another operation is running')
        lock=self.state/'operation.lock';handle=None
        try:
            handle=lock.open('x');ensure_closed();status=self.check_build(strict=True)
            if not status['ok']:raise ValueError('; '.join(status['errors']))
            if any(shutil.disk_usage(p).free<80_000_000 for p in (self.state,self.game)):raise ValueError('At least80 MB of free space is required for staging and verified backups')
            layout,hashes=self.build(selections,progress)
            # Validate again immediately before file replacement, including all
            # tracked files that this two-file operation does not replace.
            status=self.check_build(strict=True)
            if not status['ok']:raise ValueError('; '.join(status['errors']))
            original={p:self.disk['expected'][p] for p in hashes};transaction=self.state/'transactions'/layout.name
            pending={'candidate':str(layout),'transaction':str(transaction),'originals':original,'candidates':hashes,'old_profile':self.disk,'new_selections':selections}
            save_json(self.state/'pending.json',pending);self.pending=pending
            progress('Backing up and applying; resource index is installed last')
            result=Trial(self.game,layout,transaction,original,hashes).apply()
            expected=dict(self.disk['expected']);expected.update(hashes)
            profile={'selections':selections,'expected':expected,'generation':layout.name,'last_transaction':str(transaction)}
            save_json(self.state/'profile.json',profile);self.disk=profile
            (self.state/'pending.json').unlink();self.pending=None
            return {'applied':len(selections),'generation':layout.name,'backup':result['transaction']['backup_id']}
        finally:
            if handle:handle.close();lock.unlink(missing_ok=True)
            self.mutex.release()

    def recover(self):
        if not self.mutex.acquire(blocking=False):raise ValueError('Another operation is running')
        try:
            pending=self.read('pending.json',None)
            if not pending:raise ValueError('No interrupted operation to recover')
            ensure_closed();t=Trial(self.game,Path(pending['candidate']),Path(pending['transaction']),pending['originals'],pending['candidates'])
            if t.state_file.exists():t.restore()
            elif any(sha_file(self.game/p)!=h for p,h in pending['originals'].items()):raise ValueError('Unknown state; original bytes are not installed')
            save_json(self.state/'profile.json',pending['old_profile']);self.disk=pending['old_profile'];(self.state/'pending.json').unlink();self.pending=None
            # Only remove the abandoned application lock after verified recovery.
            (self.state/'operation.lock').unlink(missing_ok=True)
            return {'recovered':True}
        finally:self.mutex.release()

    def baseline_active(self):
        data=self.read('baseline-active.json',None)
        return data if data is not None else json.loads((self.resources/'active.json').read_text(encoding='utf8'))
