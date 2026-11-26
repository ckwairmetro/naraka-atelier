"""Catalogue-wide presentation compiler with explicit native compatibility."""
import copy,gzip,json
from collections import defaultdict
from core import Engine,COMMON,SHOW,EXTRA,W_FIELDS,save_json
from canonical_engine import CanonicalEngine
from native_edit import Session,CommonEditor
from advanced_recipes import hair,voice,music,pin_number
from effect_recipes import compile_effects

class FullEngine(CanonicalEngine):
    def display_order(self):
        if not hasattr(self,'_display_order'):
            self._display_order=json.loads((self.resources/'installed-order.json').read_text(encoding='utf8'))
        return self._display_order
    def resolve_features(self,features=None):
        if features is None:
            features=self.disk.get('features')
            if features is None:
                name=self.disk.get('experiment',{}).get('name','').lower()
                features={'global_reveal':'global' in name and 'reveal' in name}
        if not isinstance(features,dict) or set(features)-{'global_reveal'}:raise ValueError('Unknown appearance feature settings')
        if 'global_reveal' in features and type(features['global_reveal']) is not bool:raise ValueError('Reveal hidden cosmetics must be on or off')
        return {'global_reveal':features.get('global_reveal',False)}
    def skill_scope(self,id):
        r=self.row('SkillEffectCustom','SkillEffectCustom_SkillEffect',id)
        if r['_TalentSkillID']:return ('talent',r['_TalentSkillID'])
        if r['_CustomSkillInfo']:return ('custom',r['_CustomSkillInfo'])
        return ('effect',id)
    def audit(self):
        Engine.audit(self)
        counts=defaultdict(lambda:{'total':0,'available':0,'blocked':0})
        for i in self.items.values():
            i['support']['roles']=['source'] if i.get('synthetic') else ['target'] if i['c'] in ('skill','effect','music') else ['source','target']
            if i.get('synthetic'):continue
            c=counts[i['c']];c['total']+=1;c['available' if i['support']['available'] else 'blocked']+=1
        result=dict(counts);save_json(self.state/'catalogue-coverage.json',result);return result
    def effective_weapon(self,source,selections=()):
        for collection in (selections,self.baseline_active()):
            for s in collection:
                if s['source']==source and self.items.get(s['target'],{}).get('c')=='weapon':return self.items[s['target']]['id']
        return self.items[source]['id']
    def effect_fits_weapon(self,visual,effect):
        row=self.row('WeaponSkin','WeaponSkin_SkinBattleEffect',effect);suitable=row['_SuitableWeaponSkin']
        return not suitable or visual in suitable or effect in (self.row('WeaponSkin','WeaponSkin_WeaponSkin',visual)['_SkinEffectIDs'] or [])

    def load_items(self):
        super().load_items()
        # Folded upgrades omit some display metadata in the ZIP. Restore their
        # family/hero/slot from native rows and the explicit parent level list.
        for parent in list(self.items.values()):
            for level in parent.get('lv',[]) or []:
                child=self.items.get(parent['c']+':'+str(level.get('id')))
                if child:
                    for k in ('w','h','s'):
                        if k not in child and k in parent:child[k]=copy.deepcopy(parent[k])
                    if not child.get('en') and level.get('nameEn'):child['en']=level['nameEn']
        families={self.row('WeaponSkin','WeaponSkin_WeaponSkin',i['id'])['_WeaponTypePresentation']:i['w'] for i in self.items.values() if i['c']=='weapon' and i.get('w')}
        for item in self.items.values():
            if not item.get('en'):item['en']=item.get('zh') or str(item['id']);item['english_fallback']=True
            if item['c']=='weapon' and not item.get('w'):item['w']=families.get(self.row('WeaponSkin','WeaponSkin_WeaponSkin',item['id'])['_WeaponTypePresentation'])
            if item['c']=='accessory':
                row=self.row('OrnamentItem','OrnamentItem_OrnamentItem',item['id'])
                item.setdefault('s',row['_OrnamentType']);item.setdefault('h',row['_ValidHeroList'])
            if item['c']=='hair':
                row=self.row('HairItem','HairItem_Hair',item['id']);item['_dyeGroups']={}
                for family,ids in enumerate(row['_HighlightDyeings'] or []):
                    for id in ids:
                        group=self.row('HairHighlightDyeing','HairHighlightDyeing_PartGroup',id)
                        item['_dyeGroups'][str(id)]='底色' if family==0 else group['_PartGroupName'].replace('【占坑】','')
        for h in self.catalogue['heroes']:
            key='voice:default:'+str(h['id'])
            self.items[key]={'key':key,'id':'default:'+str(h['id']),'c':'voice','zh':'默认语音','en':'Default voice','h':[h['id']],'q':1,'synthetic':True}
        self.items['music:default']={'key':'music:default','id':'default','c':'music','zh':'默认战斗音乐','en':'Default battle music','q':1,'synthetic':True}
        # A slot with no owned accessory still needs a legitimate receiver.
        # Its cosmetic attachment is carried by an owned source outfit's
        # native built-in ornament list; no inventory item is granted.
        slots={(h,i['s']) for i in self.items.values() if i['c']=='accessory' for h in i.get('h',[])}
        for hero,slot in slots:
            outfits=[i for i in self.items.values() if i['c']=='outfit' and hero in i.get('h',[])]
            if not outfits:continue
            receiver=min(outfits,key=lambda i:(i.get('q',1),int(i['id'])))
            key=f'accessory:empty:{hero}:{slot}'
            self.items[key]={'key':key,'id':f'empty:{hero}:{slot}','c':'accessory','h':[hero],'s':slot,'q':1,'synthetic':True,'receiver':receiver['id'],'zh':'空槽 · '+receiver['zh'],'en':'Empty slot · equip source outfit '+(receiver.get('en') or receiver['zh'])}
        self.skill_groups=defaultdict(list)
        for id in self.rows['SkillEffectCustom']['SkillEffectCustom_SkillEffectGroup']:
            for skill in self.row('SkillEffectCustom','SkillEffectCustom_SkillEffectGroup',id)['_SkillEffects'] or []:self.skill_groups[skill].append(id)
        self.effect_families=defaultdict(set)
        for item in self.items.values():
            if item['c']=='weapon':
                for fx in item.get('fx',[]):self.effect_families[fx].add(item['w'])
        self.effect_types=defaultdict(set)
        for item in self.items.values():
            if item['c']=='effect' and item.get('kind')=='weapon':self.effect_types[item['type']]|=self.effect_families[str(item['id'])]
        for item in self.items.values():
            if item['c']=='effect' and item.get('kind')=='weapon':item['_weaponFamilies']=sorted(self.effect_types[item['type']])
        talents=defaultdict(set)
        for item in self.items.values():
            if item['c']=='skill':
                talents[self.skill_scope(item['id'])].add(str(item['skill']))
        for item in self.items.values():
            if item['c']=='skill':
                item['_effectGroups']=sorted(self.skill_groups[item['id']])
                members={item['id']}
                for group in self.skill_groups[item['id']]:members.update(self.row('SkillEffectCustom','SkillEffectCustom_SkillEffectGroup',group)['_SkillEffects'] or [])
                item['_affectedSkills']=sorted({key for id in members for key in talents[self.skill_scope(id)]})
            if item['c']=='effect':
                owners=[i for i in self.items.values() if i['c']==item['kind'] and str(item['id']) in (i.get('fx') or [])]
                item['_owners']=[i['id'] for i in owners]
                item['_ownerHeroes']=sorted({h for i in owners for h in i.get('h',[])})
                if item['kind']=='weapon':item['_requiredModels']=self.row('WeaponSkin','WeaponSkin_SkinBattleEffect',int(item['id'][1:]))['_SuitableWeaponSkin'] or []
                item['_rarities']=sorted({i['q'] for i in owners if i.get('q')},reverse=True)

    def intrinsic(self,item):
        c=item['c'];id=item['id']
        try:
            if item.get('synthetic'):return None
            if c=='outfit':
                info=self.general['outfits'].get(str(id))
                if not info or not info['temps']:return 'Native outfit template is missing'
                for t in info['temps']:
                    for p in t['parts']:
                        if p.get('battle',{}).get('path') not in self.assets:return 'Native outfit prefab is missing'
            elif c=='weapon':
                self.row('WeaponSkin','WeaponSkin_WeaponSkin',id);self.row('WeaponSkin','WeaponSkin_WeaponBattleSkin',id)
            elif c=='hair':
                row=self.row('HairItem','HairItem_Hair',id)
                if not row['_HairConfigs']:return 'Native hair has no visual variant'
                for v in row['_HairConfigs']:
                    if self.row('HairConfig','HairConfig_HairVisual',v)['_CosmeticAsset'] not in self.cosmetic_keys:return 'Native hair cosmetic key is missing'
            elif c in ('accessory','grapple'):
                cfg=self.row('OrnamentItem','OrnamentItem_OrnamentItem',id)['_ExtraConfigID'];self.row('OrnamentConfig','OrnamentConfig_OrnamentConfig',cfg)
            elif c in SHOW:self.row('ShowOffItemConfig','ShowOffItemConfig_'+SHOW[c],id)
            elif c in EXTRA:
                t,s,_=EXTRA[c];self.row(t,s,id)
            elif c=='effect':self.row('WeaponSkin' if item['kind']=='weapon' else 'FashionConfig',('WeaponSkin' if item['kind']=='weapon' else 'FashionConfig')+'_SkinBattleEffect',int(str(id)[1:]))
            elif c=='skill':self.row('SkillEffectCustom','SkillEffectCustom_SkillEffect',id)
            elif c=='voice':self.row('HeroVoice','HeroVoice_VoicePacket',id)
            elif c=='music':self.row('HeroVoice','HeroVoice_BattleBackgroundMusic',id)
            else:return 'Unknown catalogue category'
            if item.get('z') and not (self.resources/'rare_rules'/(str(id)+'.json.gz')).exists():return 'Native numbered rule asset is missing'
        except (KeyError,ValueError) as exc:return 'Native resource unresolved: '+str(exc)
        return None

    def variant_reason(self,src,tgt,variant):return None

    def compatible(self,src,tgt,hero=None):
        if src['key']==tgt['key']:
            only=src['c']=='weapon'
            return None if only else 'Choose a different target'
        for i in (src,tgt):
            reason=self.intrinsic(i)
            if reason:return reason
        c=tgt['c']
        if c=='effect':
            if src['c']!=tgt['kind']:return 'Select an owned '+tgt['kind']+' as the effect receiver'
            if tgt['kind']=='weapon' and src.get('w') not in self.effect_types[tgt['type']]:return 'Effect trigger belongs to another weapon family'
            if tgt['kind']=='outfit' and hero is not None and src.get('h') and int(hero) not in src['h']:return 'Select the source outfit hero'
            return None
        if c=='skill':
            if src['c']!='outfit':return 'Select an owned outfit as the skill-effect receiver'
            if hero is None or int(hero) not in set(src.get('h',[]))&set(tgt.get('h',[])):return 'Skill effect belongs to another hero'
            return None
        if src['c']!=c:return 'Categories differ'
        if c=='music':return None
        if c=='weapon':
            if not src.get('w') or src.get('w')!=tgt.get('w'):return 'Weapon families differ'
            for section,field in (('WeaponSkin_WeaponSkin','_WeaponTypePresentation'),('WeaponSkin_WeaponBattleSkin','_WeaponItemType')):
                if self.row('WeaponSkin',section,src['id'])[field]!=self.row('WeaponSkin',section,tgt['id'])[field]:return 'Native weapon classes differ'
            return None
        if c in ('background','pose','platform'):
            if src.get('h') and (hero is None or int(hero) not in src['h']):return 'Source showcase item does not support this hero'
            if tgt.get('h') and (hero is None or int(hero) not in tgt['h']):return 'Target showcase item does not support this hero'
            return None
        if c not in EXTRA and c not in ('background','pose','platform'):
            if hero is None or int(hero) not in set(src.get('h',[]))&set(tgt.get('h',[])):return 'Both items must support this hero'
        if c in ('accessory','grapple'):
            if src.get('s')!=tgt.get('s'):return 'Attachment slots differ'
            if src.get('synthetic'):return None
            a=self.row('OrnamentItem','OrnamentItem_OrnamentItem',src['id'])['_ExtraConfigID'];b=self.row('OrnamentItem','OrnamentItem_OrnamentItem',tgt['id'])['_ExtraConfigID']
            # The full target row supplies its native loader type and binding
            # metadata. Keeping the source's prop loader would skip skinning
            # for human ornaments such as tails and veils.
        if c=='outfit':
            a=self.general['outfits'][str(src['id'])]['temps'][0];b=self.general['outfits'][str(tgt['id'])]['temps'][0]
            if a['body_size']!=b['body_size']:return 'Native actor body families differ'
        return None

    def recipes(self,s):
        src,tgt=self.items[s['source']],self.items[s['target']];c=tgt['c'];a,b=src['id'],tgt['id']
        if src['key']==tgt['key']:return []
        if c in ('outfit','hair','skill','effect','voice','music'):return []
        if c=='weapon':return [('WeaponSkin','WeaponSkin_WeaponSkin',int(a),int(b),W_FIELDS),('WeaponSkin','WeaponSkin_WeaponBattleSkin',int(a),int(b),{'_WeaponTempIDList','_DropWeaponPrefabPath','_ReplaceRangeAgentModelId','_WeaponCustomDatas','_WeaponIcon','_BattleItemIcon'})]
        if c in ('accessory','grapple'):
            if src.get('synthetic'):return []
            ac=self.row('OrnamentItem','OrnamentItem_OrnamentItem',a)['_ExtraConfigID'];bc=self.row('OrnamentItem','OrnamentItem_OrnamentItem',b)['_ExtraConfigID']
            jobs=[('OrnamentConfig','OrnamentConfig_OrnamentConfig',ac,bc,set(self.row('OrnamentConfig','OrnamentConfig_OrnamentConfig',bc))-{'_ID','_Description'}),('OrnamentItem','OrnamentItem_OrnamentItem',a,b,{'_Icon','_ReplaceHair','_FacePartReplace','_ColorCustomID'})]
            if ac in self.rows['OrnamentConfig']['OrnamentConfig_ChainArrow'] and bc in self.rows['OrnamentConfig']['OrnamentConfig_ChainArrow']:jobs.append(('OrnamentConfig','OrnamentConfig_ChainArrow',ac,bc,set(self.row('OrnamentConfig','OrnamentConfig_ChainArrow',bc))-{'_ID'}))
            return jobs
        if c=='pose':
            sec='ShowOffItemConfig_ShowAction';row=self.row('ShowOffItemConfig',sec,b)
            allowed={'_StateName','_ItemIconPath','_UIWeaponID','_UIWeaponStateName','_UIWeaponDataID','_IsGroupAction','_CoupleOverrideList','_TrioOverrideList'}
            return [('ShowOffItemConfig',sec,a,b,allowed&set(row))]
        return Engine.recipes(self,s)

    def validate(self,selections):
        if not isinstance(selections,list) or len(selections)>200:raise ValueError('Profile must contain at most200 selections')
        seen=set();jobs=[];writes={};models=set();targets=set()
        for s in selections:
            if not isinstance(s,dict) or set(s)-{'source','target','hero','options'}:raise ValueError('Unknown selection fields')
            if s.get('source') not in self.items or s.get('target') not in self.items:raise ValueError('Unknown catalogue item')
            src,tgt=self.items[s['source']],self.items[s['target']];reason=self.compatible(src,tgt,s.get('hero'))
            if reason:raise ValueError(reason)
            if not isinstance(s.get('options',{}),dict):raise ValueError('Options must be an object')
            options=s.get('options',{});schema={c['key']:c for c in self.controls(tgt['key'],options.get('variant',0))}
            # v0.2.2 stored this switch. Keep old profiles valid; the confirmed
            # presentation initialization now always runs for numbered weapons.
            if tgt['c']=='weapon' and tgt.get('z'):
                schema['preview_colours']={'type':'enum','values':[{'value':0},{'value':1}]}
            if set(options)-set(schema):raise ValueError('Unsupported options for this target: '+str(set(options)-set(schema)))
            for key,value in options.items():
                c=schema[key]
                if c['type']=='enum':
                    allowed=[v['value'] for v in c['values']]
                    if value not in allowed or type(value) is bool or type(value) is float:raise ValueError('Invalid selection for '+key)
                if c['type']=='numbers':
                    if not isinstance(value,list) or len(value)!=len(c['fields']):raise ValueError('Incorrect number of values for '+key)
                    for v,f in zip(value,c['fields']):
                        if type(v) not in (int,float) or not f['min']<=v<=f['max'] or key=='numbers' and type(v) is not int:raise ValueError('Number outside native range for '+key)
                if c['type']=='colors' and (not isinstance(value,list) or len(value) not in (1,3) or any(type(v) is not int or v not in [x['value'] for x in c['values']] for v in value)):raise ValueError('Invalid native palette selection')
                if c['type']=='regions' and (not isinstance(value,list) or not value or any(type(v) is not int or not 0<=v<8 for v in value)):raise ValueError('Invalid authored hair regions')
            if tgt['c']=='hair':
                from hair_studio import validate as validate_dye
                validate_dye(self,tgt,options)
            if tgt.get('z'):
                from advanced_recipes import numbered_recipe
                numbered_recipe(self,tgt,options)
            slot=('kill' if tgt['kind']=='outfit' else tgt['type']) if tgt['c']=='effect' else tgt.get('skill') if tgt['c']=='skill' else tgt['c']
            identity=(s['source'],slot)
            if identity in seen:raise ValueError('Two selections write the same receiver slot')
            seen.add(identity)
            if tgt['c'] in ('weapon','hair','outfit','accessory','grapple') and s['source']!=s['target']:models.add(s['source']);targets.add(s['target'])
            for t,sec,a,b,fs in self.recipes(s):
                for f in fs:
                    key=(t,sec,a,f);v=self.row(t,sec,b)[f]
                    if key in writes and writes[key]!=v:raise ValueError('Selections conflict through shared native rows')
                    writes[key]=v
                jobs.append((t,sec,a,b,fs))
        if models&targets:raise ValueError('Chained or cyclic model swaps are not supported')
        advanced={}
        def claim(key,value):
            if key in advanced and advanced[key]!=value:raise ValueError('Selections require different appearances for the same shared native resource')
            advanced[key]=value
        for s in selections:
            a,b=self.items[s['source']],self.items[s['target']];o=s.get('options',{})
            if b['c']=='music':claim(('global-music',),b['id'])
            if b.get('z'):
                default=[f['default'] for f in self.controls(b['key'])[0]['fields']]
                claim(('numbers',b['id']),json.dumps(o.get('numbers',default),sort_keys=True))
            if b.get('fm'):claim(('form',b['id']),o.get('form',0))
            if b['c']=='hair':
                dst=self.row('HairItem','HairItem_Hair',b['id'])['_HairConfigs'][o.get('variant',0)]
                visual=self.row('HairConfig','HairConfig_HairVisual',dst)
                for src in self.row('HairItem','HairItem_Hair',a['id'])['_HairConfigs']:
                    claim(('hair-visual',src),tuple(visual[k] for k in ('_CosmeticAsset','_HairIconPath','_IconPath')))
                claim(('hair-custom',visual['_CosmeticAsset']),json.dumps({k:o.get(k) for k in ('color_mode','colors','hsv','sliders','parts','regions','hair_effect')},sort_keys=True))
        paths={};roots={}
        for s in selections:
            a,b=self.items[s['source']],self.items[s['target']]
            if b['c']!='outfit':continue
            variant=s.get('options',{}).get('variant',0)
            source=self.general['outfits'][str(a['id'])]['temps'][0]['parts'][0]['battle']['path']
            target=self.general['outfits'][str(b['id'])]['temps'][variant]['parts'][0]['battle']['path']
            if source in paths and paths[source]!=target or target in roots and roots[target]!=source:raise ValueError('Outfit selections share a native source path or target binding context')
            paths[source]=target;roots[target]=source
        changed_sources={a for a,b in paths.items() if a!=b};changed_targets={b for a,b in paths.items() if a!=b}
        if changed_sources&changed_targets:raise ValueError('Chained outfit prefab aliases conflict')
        skill_scopes=[]
        for s in selections:
            target=self.items[s['target']]
            if target['c']!='skill':continue
            groups=set(self.skill_groups[int(target['id'])]);scope=set()
            for g in groups:
                ids=self.row('SkillEffectCustom','SkillEffectCustom_SkillEffectGroup',g)['_SkillEffects'] or []
                scope|={self.skill_scope(i) for i in ids}
            if not scope:scope={self.skill_scope(int(target['id']))}
            for source,old_groups,old_scope in skill_scopes:
                if source==s['source'] and groups!=old_groups and scope&old_scope:raise ValueError('These native skill-effect families overlap; choose one appearance family for those variants')
            skill_scopes.append((s['source'],groups,scope))
        for s in selections:
            tgt=self.items[s['target']]
            if tgt['c']=='effect' and tgt['kind']=='weapon':
                row=self.row('WeaponSkin','WeaponSkin_SkinBattleEffect',int(str(tgt['id'])[1:]));suitable=row['_SuitableWeaponSkin']
                visual=self.effective_weapon(s['source'],selections)
                if not self.effect_fits_weapon(visual,int(str(tgt['id'])[1:])):raise ValueError('This effect requires its native weapon model; add that model swap first')
        return jobs

    def build(self,selections,progress=lambda s:None):
        jobs=self.validate(selections);layout,_=Engine.build(self,[],progress);session=Session(self,layout);proof=[]
        try:
            common=CommonEditor(self,session.edit(COMMON).cab())
            for t,sec,a,b,fs in jobs:common.patch(t,sec,a,{k:self.row(t,sec,b)[k] for k in fs})
            ordered=sorted(selections,key=lambda s:0 if self.items[s['target']]['c']=='outfit' else 1)
            for n,s in enumerate(ordered,1):
                tgt=self.items[s['target']];c=tgt['c'];progress(f'Compiling {n}/{len(ordered)} · '+c+' '+str(tgt['id']))
                if c=='outfit':
                    from outfit_recipes import outfit
                    outfit(self,session,common,s,proof)
                elif c=='hair':hair(self,session,common,s,proof)
                elif c=='weapon' and tgt.get('fm'):
                    from native_forms import stage_form
                    # Native status defaults also cover controllers referenced
                    # through external prefab loaders. Keep every weapon
                    # controller/event ID and its opaque native data intact.
                    stage_form(self,session,common,int(self.items[s['source']]['id']),int(tgt['id']),[],s.get('options',{}).get('form',0),proof,shared_default=True)
                elif c=='voice':voice(self,common,s,proof)
                elif c=='music':music(self,session,s,proof)
                elif c=='accessory' and self.items[s['source']].get('synthetic'):
                    source=self.items[s['source']];receiver=s.get('options',{}).get('receiver',source['receiver'])
                    if isinstance(receiver,str) and receiver.startswith('outfit:'):receiver=int(receiver.split(':')[1])
                    if int(s['hero']) not in self.items['outfit:'+str(receiver)].get('h',[]):raise ValueError('Empty-slot carrier outfit belongs to another hero')
                    row=common.get('FashionConfig','FashionConfig_FashionBody',receiver)
                    config=self.row('OrnamentItem','OrnamentItem_OrnamentItem',tgt['id'])['_ExtraConfigID']
                    ids=list(row['_OrnamentConfigIDs'] or [])
                    if config not in ids:ids.append(config)
                    changes={'_OrnamentConfigIDs':ids};ornament=self.row('OrnamentItem','OrnamentItem_OrnamentItem',tgt['id'])
                    if ornament['_FacePartReplace']:changes['_FacePartReplace']=ornament['_FacePartReplace']
                    replacement=ornament['_ReplaceHair']
                    if type(replacement) is int and replacement in self.rows['HairConfig']['HairConfig_HairVisual']:changes['_HairID']=replacement
                    common.patch('FashionConfig','FashionConfig_FashionBody',receiver,changes)
                    proof.append({'type':'empty_accessory_slot','hero':int(s['hero']),'receiver_outfit':receiver,'ornament_config':config,'slot':source['s']})
                elif c=='effect' and tgt['kind']=='outfit':
                    id=int(str(tgt['id'])[1:]);owner=next((i for i in self.rows['FashionConfig']['FashionConfig_FashionBody'] if id in (self.row('FashionConfig','FashionConfig_FashionBody',i)['_SkinEffectIDs'] or [])),None)
                    effect=self.row('FashionConfig','FashionConfig_FashionBody',owner)['_KillEffect'] if owner else ''
                    common.patch('FashionConfig','FashionConfig_FashionBody',int(self.items[s['source']]['id']),{'_KillEffect':effect})
                if tgt.get('z'):pin_number(self,session,tgt,s.get('options',{}),proof)
                if c=='weapon' and tgt.get('z'):
                    # The standalone presentation camera calls ApplyMutateID
                    # only when getRareSkinConfigByItem(source,20) succeeds.
                    # Keep source inventory identity; add a local display-only
                    # descriptor, with exchange/purchase operations disabled.
                    source=int(self.items[s['source']]['id']);sec='RareSkin_RareSkin'
                    existing=[self.row('RareSkin',sec,i) for i in self.rows['RareSkin'][sec] if self.row('RareSkin',sec,i)['_ItemId']==source and self.row('RareSkin',sec,i)['_ItemType']==20]
                    if not existing:
                        template=tgt['z']['rareSkinId'];id=common.alloc('RareSkin',sec)
                        changes={'_ItemId':source,'_CanExchange':False,'_TransactConditionList':None,'_HasUuid':False,'_CanReanme':False,'_CanRandomShow':False,'_RenameCoin':0,'_RenameGold':0,'_VariationItem':None,'_RevertItem':None,'_RestoreItem':None,'_RecycleEnable':False,'_ImprintTargetEnable':False,'_ImprintMaterialEnable':False}
                        common.patch('RareSkin',sec,id,changes,template=template)
                        proof.append({'type':'standalone_preview_colour_initialization','source':source,'target':tgt['id'],'descriptor':id,'account_state_changed':False,'paid_operations_disabled':True})
            compile_effects(self,session,common,selections,proof)
            features=getattr(self,'_active_features',self.resolve_features())
            if features['global_reveal']:
                from global_reveal import stage_reveal
                progress('Revealing hidden cosmetics in their native menus')
                proof.append(stage_reveal(self,common))
            common.flush();hashes=session.finish(progress)
            report={'passed':True,'selections':selections,'features':features,'hashes':hashes,'advanced':proof,'native_rows':common.proof,'bundles':session.proofs,'base_files':session.base_refs,'before':session.before,'native_tested':False}
            save_json(layout/'validation.json',report);return layout,hashes
        except Exception:
            for b in session.editors.values():b.close()
            raise

    def controls(self,key,variant=0):
        item=self.items[key];c=item['c'];controls=[]
        def enum(key,label,values,default=None):controls.append({'key':key,'label':label,'type':'enum','values':values,'default':default})
        if c=='accessory':
            outfits=[i for i in self.items.values() if i['c']=='outfit' and set(item.get('h',[]))&set(i.get('h',[]))]
            outfits.sort(key=lambda i:(i.get('q',1),int(i['id'])))
            if outfits:enum('receiver','Empty-slot source only: equip this carrier outfit',[{'value':i['key'],'label':i['zh']+' · '+(i.get('en') or '')} for i in outfits],outfits[0]['key'])
        if item.get('z'):
            r=json.load(gzip.open(self.resources/'rare_rules'/(str(item['id'])+'.json.gz'),'rt',encoding='utf8'))
            controls.append({'key':'numbers','label':'星格号码 / Appearance numbers','type':'numbers','fields':[{'label':s['zh'],'min':s['range'][0],'max':s['range'][1],'default':int(r['default_code'][s['digitPos'][0]:s['digitPos'][1]+1])} for s in item['z']['slots']]})
        if c=='outfit':
            ts=self.general['outfits'][str(item['id'])]['temps']
            if len(ts)>1:enum('variant','服装变体 / Outfit variant',[{'value':n,'label':'Default appearance' if n==0 else 'Alternate appearance '+str(n+1)} for n,t in enumerate(ts)],0)
            if item.get('fm'):enum('form','固定形态 / Form',[{'value':n,'label':f['zh']} for n,f in enumerate(item['fm']['forms'])],0)
        if c=='weapon' and item.get('fm'):enum('form','固定形态 / Form',[{'value':n,'label':f['zh']} for n,f in enumerate(item['fm']['forms'])],0)
        if c=='hair':
            row=self.row('HairItem','HairItem_Hair',item['id'])
            if len(row['_HairConfigs'])>1:enum('variant','发型变体 / Variant',[{'value':n,'label':'Style '+str(n+1)} for n,v in enumerate(row['_HairConfigs'])],0)
            fx=[self.row('HairEffect','HairEffect_Effect',i) for i in self.rows['HairEffect']['HairEffect_Effect']]
            fx=[r for r in fx if r['_EffectType']==row['_HairEffectType']]
            if fx:enum('hair_effect','发型特效 / Hair effect',[{'value':'','label':'Native default'}]+[{'value':r['_ID'],'label':r['_Name']} for r in fx],'')
            from hair_studio import studio_controls
            controls.extend(studio_controls(self,item,variant))
        return controls
