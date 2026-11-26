"""Native presentation recipes shared by the catalogue compiler."""
import copy,gzip,json,struct
from collections import defaultdict
from pathlib import Path
from native_rule_pin import pin_rule_config

F=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]

def numbered_recipe(engine,item,options):
    if not hasattr(engine,'numbered_rules'):engine.numbered_rules={};engine.numbered_plans={}
    if item['id'] not in engine.numbered_rules:
        with gzip.open(engine.resources/'rare_rules'/(str(item['id'])+'.json.gz'),'rt',encoding='utf8') as f:engine.numbered_rules[item['id']]=json.load(f)
    r=engine.numbered_rules[item['id']]
    slots=item['z']['slots'];values=options.get('numbers')
    if values is None:code=r['default_code']
    else:
        if len(values)!=len(slots):raise ValueError('Provide one number per constellation slot')
        digits=['0']*r['tree']['usedDigitCount']
        for s,v in zip(slots,values):
            lo,hi=s['range']
            if type(v) is not int or not lo<=v<=hi:raise ValueError('Constellation number outside native range')
            a,b=s['digitPos'];digits[a:b+1]=str(v).zfill(b-a+1)
        code=''.join(digits)
    key=(item['id'],code)
    if key not in engine.numbered_plans:engine.numbered_plans[key]=pin_rule_config(r['tree'],code)
    tree,p=engine.numbered_plans[key]
    return r,code,tree,p

def pin_number(engine,session,item,options,proof):
    r,code,tree,p=numbered_recipe(engine,item,options)
    _,cab,entry=session.asset(r['path']);cab.put(entry['asset']['m_PathID'],tree)
    proof.append({'type':'numbered','item':item['id'],'code':code,'rules':len(p['rules'])})

def color_tree(tree,palettes,options):
    t=copy.deepcopy(tree);mode=options.get('color_mode','solid')
    indices=options.get('colors',[0,0,0])
    if len(indices)!=3 or any(type(i) is not int or not 0<=i<len(palettes) for i in indices):raise ValueError('Invalid native hair palette')
    if mode=='solid':indices=[indices[0]]*3
    if mode not in ('solid','gradient','streaks'):raise ValueError('Unknown hair colour mode')
    colors=dict(zip('ABC',[palettes[i] for i in indices]));sliders=options.get('sliders',[35,38,100])
    if len(sliders)!=3 or any(type(i) not in (int,float) or not 0<=i<=100 for i in sliders):raise ValueError('Hair sliders must be between0 and100')
    a,c,blur=F(1-F(sliders[0]/100)),F(sliders[1]/100),F(sliders[2]/100)
    selected=options.get('regions',list(range(8))) if mode=='streaks' else list(range(8))
    if not selected or any(type(i) is not int or not 0<=i<8 for i in selected):raise ValueError('Choose native hair regions0–7')
    for hair in t['serializedCustomHairData']:
        if not hair.get('USE_NEW_HAIR'):raise ValueError('This hair uses the legacy shader; native iridescent palette cannot be promised')
        groups=[hair['BaseHighLightingData'],*hair['unpackedPartData']]
        for n,g in enumerate(groups):
            if n and n-1 not in selected:continue
            if n:g['HairIDs']=0
            g['HighLightingAmount']=1.0;g['HighLightingBlur']=blur
            for region,weight in [('A',a),('B',1.0),('C',c)]:
                area=g['HighLightingData'+region];area['HighLightingWeight']=weight
                for k in area['HighLightingColorData']:
                    if k!='Description':area['HighLightingColorData'][k]=copy.deepcopy(colors[region][k])
                if 'HighLightingColor'+region in g:g['HighLightingColor'+region]=copy.deepcopy(colors[region]['HighLightingColor'])
            for k in colors['B']:
                if k!='Description' and k in g:g[k]=copy.deepcopy(colors['B'][k])
            for k,v in [('HighLightingColorBWeight',a),('HighLightingColorCWeight',c)]:
                if k in g:g[k]=v
        for region in 'ABC':hair['BaseColor'+region]=copy.deepcopy(colors[region]['HighLightingColor'])
        hair.update(BaseColorBWeight=a,BaseColorCWeight=c,BaseColorBlur=blur)
        for k in ('Ks','KsBoost','KsWidth','ScatterPower','BackLit','SoftDetailShadowStrength','SoftMainShadowStrength','GlossMapScale'):
            hair['Base'+k]=copy.deepcopy(colors['B'][k])
    return t

def walk(cab,root):
    seen=set();pending=[root]
    while pending:
        pid=pending.pop()
        if pid in seen:continue
        seen.add(pid);tree=cab.tree(pid);yield pid,tree
        for pair in tree.get('m_Component',[]):
            ptr=pair[1] if isinstance(pair,(tuple,list)) else pair.get('component',pair)
            if ptr['m_FileID']:raise ValueError('External prefab component requires resolution')
            cp=ptr['m_PathID']
            try:ct=cab.tree(cp)
            except ValueError:
                obj=cab.sf.objects[cp];node=obj.serialized_type.node
                names={n.m_Name for n in node.traverse()}
                if obj.type.name!='MonoBehaviour' or names&{'visualStatusMap','m_DefaultEffectIndex'}:raise
                # Unrelated custom native components can contain extra data
                # beyond the shipped type tree. Leave their raw bytes exact.
                continue
            yield cp,ct
            for child in ct.get('m_Children',[]):
                if child['m_FileID']:raise ValueError('External transform requires resolution')
                tr=cab.tree(child['m_PathID']);pending.append(tr['m_GameObject']['m_PathID'])

def hair(engine,session,common,s,proof):
    src,tgt=engine.items[s['source']],engine.items[s['target']];opts=s.get('options',{})
    a=engine.row('HairItem','HairItem_Hair',src['id']);b=engine.row('HairItem','HairItem_Hair',tgt['id'])
    variant=opts.get('variant',0)
    if type(variant) is not int or not 0<=variant<len(b['_HairConfigs']):raise ValueError('Invalid hair variant')
    tv=b['_HairConfigs'][variant];target=engine.row('HairConfig','HairConfig_HairVisual',tv)
    for id in a['_HairConfigs']:
        common.patch('HairConfig','HairConfig_HairVisual',id,{k:target[k] for k in ('_CosmeticAsset','_HairIconPath','_IconPath')})
    common.patch('HairItem','HairItem_Hair',src['id'],{'_UIIconPath':b['_UIIconPath']})
    info=next(v for v in engine.general['hairs'][str(tgt['id'])]['visuals'] if v['id']==tv)
    with gzip.open(engine.resources/'cosmetic-routes.json.gz','rt',encoding='utf8') as f:routes=json.load(f).get(target['_CosmeticAsset'],[])
    paths=sorted({p for r in routes for p in r['prefabs'] if p in session.assets})
    if not paths:paths=[p['path'] for p in info['prefabs'] if p['path'] in session.assets]
    if opts.get('hair_effect') is not None:
        effect=engine.row('HairEffect','HairEffect_Effect',opts['hair_effect'])
        if effect['_EffectType']!=b['_HairEffectType']:raise ValueError('Hair effect belongs to a different native controller')
        count=0
        for path in paths:
            _,cab,en=session.asset(path)
            for pid,t in walk(cab,en['asset']['m_PathID']):
                if 'm_DefaultEffectIndex' in t:t['m_DefaultEffectIndex']=effect['_NovaEffectGroupIndex'];cab.put(pid,t);count+=1
        if not count:raise ValueError('Target hair has no native effect controller')
    colored=[]
    if opts.get('color_mode'):
        palette=json.loads((engine.resources/'palette.json').read_text())
        data=sorted({p for r in routes for p in r['custom_data'] if p in session.assets})
        if not data:raise ValueError('Native wardrobe/battle hair colour resources are unresolved')
        for p in data:
            from hair_studio import dye_tree
            _,cab,en=session.asset(p);pid=en['asset']['m_PathID'];cab.put(pid,dye_tree(engine,tgt,cab.tree(pid),palette,opts));colored.append(p)
    proof.append({'type':'hair','source':src['id'],'target':tgt['id'],'variant':variant,'colored_resources':colored})

def voice(engine,common,s,proof):
    src,tgt=engine.items[s['source']],engine.items[s['target']];hero=int(s['hero'])
    source=int(src['id']) if str(src['id']).isdigit() else 0;target=int(tgt['id'])
    section='HeroVoice_TriggerEvtMap';groups=defaultdict(list);sources=defaultdict(list)
    for id in engine.rows['HeroVoice'][section]:
        r=engine.row('HeroVoice',section,id)
        if r['_ActorReferenceID']!=hero:continue
        if r['_VoicePacketId']==target:groups[r['_TriggerID']].append(r)
        if r['_VoicePacketId']==source:sources[r['_TriggerID']].append(r)
    if not sources or not groups:raise ValueError('No matching native voice triggers for this hero')
    count=0
    for trigger,rows in sources.items():
        if trigger not in groups:continue
        targets=groups[trigger]
        for n,r in enumerate(rows):
            chosen=targets[n%len(targets)]
            common.patch('HeroVoice',section,r['_ID'],{'_EventName':chosen['_EventName'],'_PreviewText':chosen['_PreviewText']});count+=1
        # Preserve each native event array as a unit (including language/event
        # layout). Extra variants get rows for this existing source trigger;
        # source packet/hero/trigger/weights remain from the native prototype.
        for chosen in targets[len(rows):]:
            id=common.alloc('HeroVoice',section)
            common.patch('HeroVoice',section,id,{'_EventName':chosen['_EventName'],'_PreviewText':chosen['_PreviewText']},template=rows[0]['_ID']);count+=1
    if not count:raise ValueError('Source and target voice packs have no shared triggers')
    proof.append({'type':'voice','source':source,'target':target,'hero':hero,'rows':count,'target_only_triggers':sorted(set(groups)-set(sources))})

def music(engine,session,s,proof):
    row=engine.row('HeroVoice','HeroVoice_BattleBackgroundMusic',int(engine.items[s['target']]['id']))
    if not row['_EventName']:raise ValueError('This music uses a skill-specific audio trigger; no ordinary battle event')
    bundle='a/8/a89c86ec6df2a5d1';cab=session.edit(bundle).cab()
    # This global resource is fingerprinted with the installed build. Avoid
    # probing unrelated custom MonoBehaviours with incompatible native schemas.
    pid=-2431296323777477540
    if cab.tree(pid).get('m_Name')!='roomtype_audio_config':raise ValueError('Battle music resource differs from reviewed build')
    t=cab.tree(pid);groups=[t['defaultRoomAudioInfo']]+[r['overrideAudioInfo'] for r in t['mapDefaultAudioInfos']]+t['roomAudioInfos']
    for r in groups:
        if r['enableBattleMusic']:r['disableRegionBattleMusic']=1;r['battleMusic'].update(type=1,eventName=row['_EventName'],stateGroup='music_battle_switch',stateParam='A')
    cab.put(pid,t);proof.append({'type':'music','target':row['_ID'],'scope':'client-wide ordinary combat music'})
