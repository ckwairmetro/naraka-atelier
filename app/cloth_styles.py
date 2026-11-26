"""Native outfit colour/style presets under canonical source part IDs."""
import copy

def stage_style(engine,session,common,source,target,variant=0):
    outfit=engine.row('FashionConfig','FashionConfig_FashionBody',target)
    groups=outfit['_ClothCustomListList']
    if not groups:return
    group=copy.deepcopy(groups[min(variant,len(groups)-1)])
    if not group:return
    sa=engine.general['outfits'][str(source)]['temps'][0]
    ta=engine.general['outfits'][str(target)]['temps'][variant]
    mapping={b['id']:a['id'] for a,b in zip(sa['parts'],ta['parts'])}
    source_actor=engine.row('CharacterConfig','CharacterConfig_ActorTemp',sa['id'])
    available=list(dict.fromkeys((source_actor['_VisualParts'] or [])+(source_actor['_OtherVisualParts'] or [])))
    registered={}
    for entry in group:
        target_part=entry['_VisualPart']
        if target_part not in mapping:
            role=engine.row('CharacterConfig','CharacterConfig_ActorVisualPart',target_part)['_BodyVisualPart']
            matches=[p for p in available if engine.row('CharacterConfig','CharacterConfig_ActorVisualPart',p)['_BodyVisualPart']==role]
            if len(matches)!=1:raise ValueError('Outfit colour preset has no unique compatible source part')
            mapping[target_part]=matches[0]
        part=mapping[target_part];entry['_VisualPart']=part
        native=common.get('CharacterConfig','CharacterConfig_ActorVisualPart',part)
        ids=registered.setdefault(part,list(native['_ClothCustomDatas'] or []))
        if entry['_ClothCustomID'] not in ids:ids.append(entry['_ClothCustomID'])
        data=engine.row('CharacterConfig','CharacterConfig_ActorClothCustomData',entry['_ClothCustomID'])
        path='assets/res/character/cloth_custom_data/'+data['_DataPath'].lower()+'.asset'
        _,cab,en=session.asset(path);pid=en['asset']['m_PathID'];tree=cab.tree(pid)
        if tree.get('prefabPath'):
            tree['prefabPath']='Assets/Res/Prefab/actor_visual_part/'+native['_PrefabPath']+'.prefab'
            cab.put(pid,tree)
    for part,ids in registered.items():
        current=common.get('CharacterConfig','CharacterConfig_ActorVisualPart',part)
        if current['_ClothCustomDatas']!=ids:common.patch('CharacterConfig','CharacterConfig_ActorVisualPart',part,{'_ClothCustomDatas':ids})
    source_row=common.get('FashionConfig','FashionConfig_FashionBody',source)
    count=len(source_row['_CharacterActorTempIDs'] or [0])
    common.patch('FashionConfig','FashionConfig_FashionBody',source,{'_ClothCustomListList':[copy.deepcopy(group) for _ in range(count)]})
