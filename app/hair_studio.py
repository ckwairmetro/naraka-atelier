"""Mode-specific local hair recipes; native capabilities are target-specific."""
import colorsys,copy,gzip,json,math,struct

F=lambda n:struct.unpack('<f',struct.pack('<f',n))[0]

def capabilities(engine,item,variant=0):
    row=engine.row('HairItem','HairItem_Hair',item['id'])
    if type(variant) is not int or not 0<=variant<len(row['_HairConfigs']):raise ValueError('Invalid hair variant')
    if not hasattr(engine,'hair_rendering'):
        engine.hair_rendering=json.load(gzip.open(engine.resources/'hair-rendering.json.gz','rt',encoding='utf8'))
    visual=engine.row('HairConfig','HairConfig_HairVisual',row['_HairConfigs'][variant])['_CosmeticAsset']
    modern=bool(engine.hair_rendering.get(visual,{}).get('modern_palette'))
    groups=[]
    for family,ids in enumerate(row['_HighlightDyeings'] or []):
        for id in ids:
            r=engine.row('HairHighlightDyeing','HairHighlightDyeing_PartGroup',id)
            params=engine.row('HairHighlightDyeing','HairHighlightDyeing_ParamGroup',r['_ParamGroupID'])['_ParamIDs']
            groups.append({'id':id,'label':r['_PartGroupName'].replace('【占坑】',''),'parts':r['_PartIDs'],'base':family==0,'intensity':102 in params,'gradient':all(p in params for p in (103,104,105,106,107,108))})
    levels=row['_HighlightDyeingFunctionLevels'] or []
    return {'modern':modern,'levels':levels,'groups':groups,'highlights':modern and 40003 in levels and any(not g['base'] for g in groups)}

def studio_controls(engine,item,variant=0):
    cap=capabilities(engine,item,variant)
    if not cap['modern']:return []
    modes=[{'value':'','label':'No local dye override'}]
    for id,value,label in [(40000,'plain','纯色 · Solid colour'),(40001,'flourish','华彩 · Flourish'),(40002,'gradient','渐变 · Gradient')]:
        if id in cap['levels']:modes.append({'value':value,'label':label})
    if 40001 in cap['levels']:modes.append({'value':'solid','label':'华彩 · Legacy uniform palette','legacy':True})
    if cap['highlights']:modes.append({'value':'streaks','label':'挑染 · Highlights'})
    tags={t['id']:t for t in engine.catalogue['hairDye']['tags']}
    palette=[{'value':x['idx'],'label':tags.get(x.get('tag'),{}).get('zh','')+'·'+x['zh']+' · '+(x.get('en') or ''),'finish':tags.get(x.get('tag'),{}).get('zh','')} for x in engine.catalogue['hairDye']['colours']]
    return [
        {'key':'color_mode','type':'enum','label':'发色模式 · Dye mode','values':modes,'default':''},
        {'key':'colors','type':'colors','label':'华彩颜色 · Palette','values':palette,'default':[0,0,0]},
        {'key':'hsv','type':'numbers','label':'纯色 · Hue / Saturation / Brightness','fields':[{'label':l,'min':0,'max':100,'default':v} for l,v in zip(('Hue','Saturation','Brightness'),(0,0,30))]},
        {'key':'sliders','type':'numbers','label':'渐变 · Gradient ranges','fields':[{'label':l,'min':0,'max':100,'default':v} for l,v in zip(('Middle range','Tip range','Transition'),(35,38,100))]},
        {'key':'parts','type':'parts','label':'挑染部位 · Authored groups','values':cap['groups'],'palette':palette,'default':[]},
        # Accepted old profiles remain readable; new UI never emits flat regions.
        {'key':'regions','type':'regions','label':'Legacy regions','default':list(range(8)),'legacy':True},
    ]

def numbers(v,n,label):
    if not isinstance(v,list) or len(v)!=n or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=100 for x in v):raise ValueError('Invalid '+label)

def validate(engine,item,options):
    mode=options.get('color_mode','');keys=set(options)&{'colors','hsv','sliders','regions','parts'}
    if not mode:
        if keys:raise ValueError('Choose a dye mode before selecting colours')
        return
    cap=capabilities(engine,item,options.get('variant',0))
    modes={m['value'] for c in studio_controls(engine,item,options.get('variant',0)) if c['key']=='color_mode' for m in c['values']}
    if mode not in modes:raise ValueError('This hairstyle/variant does not support that dye mode')
    allowed={'plain':{'hsv'},'flourish':{'colors'},'solid':{'colors','sliders','regions'},'gradient':{'colors','sliders'},'streaks':{'parts'}}[mode]
    if keys-allowed:raise ValueError('Dye fields do not belong to the selected mode')
    palette={c['idx'] for c in engine.catalogue['hairDye']['colours']}
    def recipe(r):
        m=r['mode']
        if m=='plain':numbers(r.get('hsv'),3,'solid colour')
        elif m in ('flourish','gradient','solid'):
            n=3 if m in ('gradient','solid') else 1;v=r.get('colors')
            if not isinstance(v,list) or len(v)!=n or any(type(x) is not int or x not in palette for x in v):raise ValueError('Invalid native palette selection')
            if m=='gradient':numbers(r.get('sliders'),3,'gradient ranges')
        else:raise ValueError('Unknown part dye mode')
    if mode!='streaks':
        recipe(dict(options,mode=mode));return
    parts=options.get('parts');groups={g['id']:g for g in cap['groups']}
    if not isinstance(parts,list) or not parts:raise ValueError('Choose an applicable highlight group')
    seen=set()
    for r in parts:
        if not isinstance(r,dict) or set(r)-{'group','mode','colors','hsv','sliders','intensity'}:raise ValueError('Unknown highlight fields')
        id=r.get('group')
        if type(id) is not int or id not in groups or id in seen:raise ValueError('Invalid or duplicate highlight group')
        seen.add(id);g=groups[id];m=r.get('mode')
        expected={'plain':{'hsv'},'flourish':{'colors'},'gradient':{'colors','sliders'}}.get(m)
        if expected is None or (set(r)&{'colors','hsv','sliders'})!=expected:raise ValueError('Highlight controls do not match the chosen mode')
        if m=='gradient' and not g['gradient']:raise ValueError('This highlight group does not support gradients')
        if 'intensity' in r:
            if not g['intensity']:raise ValueError('This group has no intensity control')
            numbers([r['intensity']],1,'highlight intensity')
        recipe(r)

def uniform(tree,preset=None,hsv=None):
    """Match the accepted uniform-palette fixture; plain keeps native lighting."""
    t=copy.deepcopy(tree)
    # Native normal-colour values use parameter-defined HSV limits.
    rgb=colorsys.hsv_to_rgb(F(hsv[0]/100),F(hsv[1]/100),F(F(.1)+F(F(.82)-F(.1))*F(hsv[2]/100))) if hsv is not None else None
    color={k:F(v) for k,v in zip('rgba',(*rgb,1.0))} if rgb else preset['HighLightingColor']
    for h in t['serializedCustomHairData']:
        if not h.get('USE_NEW_HAIR'):raise ValueError('Unsupported hair shader')
        for n,g in enumerate([h['BaseHighLightingData'],*h['unpackedPartData']]):
            if n:g['HairIDs']=0
            g['HighLightingAmount']=1.0
            for region in 'ABC':
                area=g['HighLightingData'+region]['HighLightingColorData']
                if preset:
                    for k in area:
                        if k!='Description':area[k]=copy.deepcopy(preset[k])
                else:area['HighLightingColor']=copy.deepcopy(color)
                if 'HighLightingColor'+region in g:g['HighLightingColor'+region]=copy.deepcopy(color)
            if preset:
                for k in preset:
                    if k!='Description' and k in g:g[k]=copy.deepcopy(preset[k])
        for r in 'ABC':h['BaseColor'+r]=copy.deepcopy(color)
        if preset:
            for k in ('Ks','KsBoost','KsWidth','ScatterPower','BackLit','SoftDetailShadowStrength','SoftMainShadowStrength','GlossMapScale'):h['Base'+k]=copy.deepcopy(preset[k])
    return t

def dye_tree(engine,item,tree,palette,options):
    from advanced_recipes import color_tree
    def styled(r):
        if r['mode']=='plain':return uniform(tree,hsv=r['hsv'])
        if r['mode'] in ('solid','flourish'):return uniform(tree,preset=palette[r['colors'][0]])
        return color_tree(tree,palette,dict(r,color_mode='gradient'))
    mode=options['color_mode']
    if mode!='streaks':return styled(dict(options,mode=mode))
    out=copy.deepcopy(tree);groups={g['id']:g for g in capabilities(engine,item,options.get('variant',0))['groups']}
    for h in out['serializedCustomHairData']:
        for p in h['unpackedPartData']:p['HairIDs']=0
    for r in options['parts']:
        full=styled(r)
        for dst,src in zip(out['serializedCustomHairData'],full['serializedCustomHairData']):
            for part in groups[r['group']]['parts']:
                if part==0:
                    for k in src:
                        if k.startswith('Base'):dst[k]=copy.deepcopy(src[k])
                    g=dst['BaseHighLightingData']
                else:g=dst['unpackedPartData'][part-1]=copy.deepcopy(src['unpackedPartData'][part-1])
                if 'intensity' in r:g['HighLightingAmount']=F(r['intensity']/100)
    return out
