"""Candidate-only same-bundle whole-prefab adapter. No installation functions.

Keep this separate from the rejected private-context generator until native
acceptance. Shared source paths deliberately remain a reported limitation.
"""
import copy
from pathlib import Path
from proto_codec import fields, row_key, delimited

ARCHIVE_PATH='assets/raw_resources/proto_bytes/custom_tags_data_archive.bytes'

def stage_outfit(engine, session, common, inventory, source, target, hero, variant=0):
    a,b=engine.items[f'outfit:{source}'],engine.items[f'outfit:{target}']
    if hero not in set(a.get('h',[])) & set(b.get('h',[])):
        raise ValueError('Source and target must support the selected hero')
    src=inventory['outfits'][str(source)]['temps'][0]
    dst=inventory['outfits'][str(target)]['temps'][variant]
    if src['body_size']!=dst['body_size'] or len(src['parts'])!=1 or len(dst['parts'])!=1:
        raise ValueError('Only equal body families with one complete main part are supported')
    sp,tp=src['parts'][0],dst['parts'][0]
    for part in (sp,tp):
        if (part['wardrobe'] or part['battle'])['path']!=part['battle']['path']:
            raise ValueError('Split wardrobe/battle templates need a separate adapter')
    canonical=engine.row('CharacterConfig','CharacterConfig_ActorVisualPart',sp['id'])
    current=common.get('CharacterConfig','CharacterConfig_ActorVisualPart',sp['id'])
    for k in ('_PrefabPath','_UICharacterPrefabPath'):
        if current[k]!=canonical[k]:raise ValueError('Canonical source lookup is already altered: '+k)
    actor=common.get('CharacterConfig','CharacterConfig_ActorTemp',src['id'])
    if actor['_VisualParts']!=engine.row('CharacterConfig','CharacterConfig_ActorTemp',src['id'])['_VisualParts']:
        raise ValueError('Canonical source visual-part identities differ')
    source_path,target_path=sp['battle']['path'],tp['battle']['path']
    sb,sc,se=session.asset(source_path);tb,tc,te=session.asset(target_path)
    if sb!=tb or sc is not tc:raise ValueError('Cross-bundle/CAB outfits are not supported by this adapter')
    context=sc.tree(se['asset']['m_PathID'])['m_Name']
    root=tc.tree(te['asset']['m_PathID'])
    target_context=root['m_Name']
    if not context or not target_context:raise ValueError('Native prefab root context is empty')
    original_root=copy.deepcopy(root);root['m_Name']=context
    ownership=getattr(session,'outfit_root_contexts',{});identity=(tb,tc.path.name,te['asset']['m_PathID'])
    if identity in ownership and ownership[identity]!=context:raise ValueError('Two outfit aliases require different contexts on the same target root')
    ownership[identity]=context;session.outfit_root_contexts=ownership
    tc.put(te['asset']['m_PathID'],root)
    ab=sc.tree(sc.abobj.path_id);old_entries=copy.deepcopy(ab['m_Container'])
    ab['m_Container']=[(p,copy.deepcopy(te) if p==source_path else v) for p,v in ab['m_Container']]
    if sum(p==source_path for p,_ in old_entries)!=1:raise ValueError('Canonical source container is ambiguous')
    sc.put(sc.abobj.path_id,ab)
    _,cab,en=session.asset(ARCHIVE_PATH);tree=cab.tree(en['asset']['m_PathID'])
    raw=tree['m_Script'].encode('utf8',errors='surrogateescape');top=fields(raw)
    rows={row_key(f['value']):f['value'] for f in top if f['number']==1}
    replacements={}
    for key,row in rows.items():
        if key.startswith(target_context+'/'):
            key2=context+key[len(target_context):]
            replacements[key2]=b''.join(delimited(1,key2.encode()) if f['number']==1 else f['raw'] for f in fields(row))
            assert [f['raw'] for f in fields(replacements[key2]) if f['number']!=1]==[f['raw'] for f in fields(row) if f['number']!=1]
    if not replacements:raise ValueError('No target native bone-binding rows')
    data=b''.join(delimited(1,replacements[row_key(f['value'])]) if f['number']==1 and row_key(f['value']) in replacements else f['raw'] for f in top)
    data+=b''.join(delimited(1,replacements[k]) for k in sorted(set(replacements)-set(rows)))
    after=[(row_key(f['value']),f['value']) for f in fields(data) if f['number']==1]
    if len(dict(after))!=len(after) or dict(after)!=(rows|replacements):raise ValueError('Binding archive scope validation failed')
    if [f['raw'] for f in fields(data) if f['number']!=1]!=[f['raw'] for f in top if f['number']!=1]:raise ValueError('Global binding data changed')
    tree['m_Script']=data.decode('utf8',errors='surrogateescape');cab.put(en['asset']['m_PathID'],tree)
    # Icon only. No FashionBody template/cloth, ActorTemp, ActorVisualPart or
    # account identity fields are written. The existing source dyes remain.
    common.patch('FashionConfig','FashionConfig_FashionBody',source,{'_UIIconPath':engine.row('FashionConfig','FashionConfig_FashionBody',target)['_UIIconPath']})
    from cloth_styles import stage_style
    stage_style(engine,session,common,source,target,variant)
    peers=[]
    for id in engine.rows['FashionConfig']['FashionConfig_FashionBody']:
        row=engine.row('FashionConfig','FashionConfig_FashionBody',id)
        if src['id'] in (row['_CharacterActorTempIDs'] or []):peers.append(id)
    return {'source':source,'target':target,'hero':hero,'variant':variant,'bundle':sb,
            'source_path':source_path,'target_path':target_path,'canonical_battle_and_ui_lookup_preserved':True,
            'actor_template_and_visual_ids_preserved':True,'target_entry':te,'target_root_id':te['asset']['m_PathID'],
            'target_root_changed_fields':[k for k in root if root[k]!=original_root[k]],
            'complete_target_components_preserved':root['m_Component']==original_root['m_Component'],
            'translated_binding_rows':len(replacements),'binding_keys':sorted(replacements),
            'shared_source_template_items':peers,'native_tested':False}
