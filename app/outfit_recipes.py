"""Full native target prefabs under canonical source battle identities."""
import copy
from pathlib import Path
from proto_codec import fields,row_key,delimited
from advanced_recipes import walk

def binding(session,source_context,target_context,seen):
    path='assets/raw_resources/proto_bytes/custom_tags_data_archive.bytes'
    _,cab,en=session.asset(path);pid=en['asset']['m_PathID'];tree=cab.tree(pid)
    raw=tree['m_Script'].encode('utf8',errors='surrogateescape');top=fields(raw)
    rows={row_key(f['value']):f['value'] for f in top if f['number']==1}
    available={k:v for k,v in rows.items() if k.startswith(target_context+'/')}
    if not available and target_context.endswith('_ui'):
        target_context=target_context[:-3];available={k:v for k,v in rows.items() if k.startswith(target_context+'/')}
    if not available:raise ValueError('Target native binding context is absent: '+target_context)
    repl={}
    for k,row in available.items():
        key=source_context+k[len(target_context):]
        value=b''.join(delimited(1,key.encode()) if f['number']==1 else f['raw'] for f in fields(row))
        if key in seen and seen[key]!=value:raise ValueError('Wardrobe/battle binding contexts conflict')
        seen[key]=value;repl[key]=value
    data=b''.join(delimited(1,repl[row_key(f['value'])]) if f['number']==1 and row_key(f['value']) in repl else f['raw'] for f in top)
    data+=b''.join(delimited(1,repl[k]) for k in sorted(set(repl)-set(rows)))
    actual=[(row_key(f['value']),f['value']) for f in fields(data) if f['number']==1]
    if len(dict(actual))!=len(actual) or dict(actual)!=(rows|repl):raise ValueError('Binding archive scope differs')
    tree['m_Script']=data.decode('utf8',errors='surrogateescape');cab.put(pid,tree)
    return len(repl)

def outfit(engine,session,common,s,proof):
    src,tgt=engine.items[s['source']],engine.items[s['target']];opts=s.get('options',{});variant=opts.get('variant',0)
    sa=engine.general['outfits'][str(src['id'])]['temps'][0];choices=engine.general['outfits'][str(tgt['id'])]['temps']
    if type(variant) is not int or not 0<=variant<len(choices):raise ValueError('Invalid native outfit variant')
    ta=choices[variant]
    # Preserve the exact accepted compiler for pairs that fit its constraints.
    from canonical_engine import CanonicalEngine
    from canonical_outfit import stage_outfit
    if not tgt.get('fm') and not CanonicalEngine.outfit_reason(engine,src) and not CanonicalEngine.outfit_reason(engine,tgt) and not CanonicalEngine.variant_reason(engine,src,tgt,variant):
        proof.append(stage_outfit(engine,session,common,engine.general,src['id'],tgt['id'],int(s['hero']),variant));return
    if sa['body_size']!=ta['body_size'] or len(sa['parts'])!=len(ta['parts']):raise ValueError('Outfit native body roles are incompatible')
    contexts={};roots=[];edits=[]
    for sp,tp in zip(sa['parts'],ta['parts']):
        current=common.get('CharacterConfig','CharacterConfig_ActorVisualPart',sp['id'])
        original=engine.row('CharacterConfig','CharacterConfig_ActorVisualPart',sp['id'])
        if current['_PrefabPath']!=original['_PrefabPath']:raise ValueError('Canonical source battle lookup was changed')
        source_battle=sp['battle']['path']
        _,source_cab,source_entry=session.asset(source_battle);source_context=source_cab.tree(source_entry['asset']['m_PathID'])['m_Name']
        battle_identity=None
        for role in ('battle','wardrobe'):
            route=tp.get(role) or tp['battle'];target_path=route['path']
            _,cab,en=session.asset(target_path);root_id=en['asset']['m_PathID'];root=cab.tree(root_id)
            identity=(session.assets[target_path],cab.path.name,root_id)
            if role=='wardrobe' and identity!=battle_identity:
                # Separate native UI meshes can have a different bone order.
                # Keep their original root/archive context; only the source UI
                # lookup points at this native UI prefab. Battle stays canonical.
                relative=engine.row('CharacterConfig','CharacterConfig_ActorVisualPart',tp['id'])['_UICharacterPrefabPath']
                if not relative:relative=target_path.removeprefix('assets/res/prefab/actor_visual_part/').removesuffix('.prefab')
                common.patch('CharacterConfig','CharacterConfig_ActorVisualPart',sp['id'],{'_UICharacterPrefabPath':relative})
                roots.append((cab,root_id));edits.append({'role':role,'source_lookup':target_path,'target':target_path,'native_ui_binding_context_preserved':True});continue
            if role=='battle':battle_identity=identity
            ownership=getattr(session,'outfit_root_contexts',{});identity=(session.assets[target_path],cab.path.name,root_id)
            if identity in ownership and ownership[identity]!=source_context:raise ValueError('Shared outfit root has conflicting source contexts')
            ownership[identity]=source_context;session.outfit_root_contexts=ownership
            target_context=root['m_Name']
            if role=='battle':lookup=source_battle
            else:
                native_ui=sp.get('wardrobe') or sp['battle']
                lookup=native_ui['path']
                if route['path']!=tp['battle']['path'] and lookup==source_battle:
                    # The ranked-tested Cyra fixture uses the native target UI
                    # path. Only the UI lookup changes; battle stays canonical.
                    lookup=target_path
                    common.patch('CharacterConfig','CharacterConfig_ActorVisualPart',sp['id'],{'_UICharacterPrefabPath':engine.row('CharacterConfig','CharacterConfig_ActorVisualPart',tp['id'])['_UICharacterPrefabPath']})
            owner=session.assets.get(lookup);target_bundle=session.assets[target_path]
            if owner!=target_bundle:
                session.records[owner]['assets'].remove(lookup);session.records[target_bundle]['assets'].append(lookup);session.assets[lookup]=target_bundle
            ab=cab.tree(cab.abobj.path_id);entries=dict(ab['m_Container'])
            if lookup in entries:ab['m_Container']=[(p,copy.deepcopy(en) if p==lookup else v) for p,v in ab['m_Container']]
            else:ab['m_Container'].append((lookup,copy.deepcopy(en)))
            cab.put(cab.abobj.path_id,ab)
            root['m_Name']=source_context;cab.put(root_id,root)
            roots.append((cab,root_id))
            edits.append({'role':role,'source_lookup':lookup,'target':target_path,'bindings':binding(session,source_context,target_context,contexts)})
    source_actor=common.get('CharacterConfig','CharacterConfig_ActorTemp',sa['id'])
    target_actor=engine.row('CharacterConfig','CharacterConfig_ActorTemp',ta['id'])
    if source_actor['_FootType']!=target_actor['_FootType']:common.patch('CharacterConfig','CharacterConfig_ActorTemp',sa['id'],{'_FootType':target_actor['_FootType']})
    target_fashion=engine.row('FashionConfig','FashionConfig_FashionBody',tgt['id'])
    fields_to_copy=('_UIIconPath','_HairID','_FacePartReplace','_OrnamentConfigIDs','_EnableTranslucentFunc','_TranslucentDisableDefault','_CameraPosName')
    common.patch('FashionConfig','FashionConfig_FashionBody',src['id'],{k:target_fashion[k] for k in fields_to_copy})
    from cloth_styles import stage_style
    stage_style(engine,session,common,src['id'],tgt['id'],variant)
    if tgt.get('fm'):
        form=opts.get('form',0);types=[]
        if form==0:
            from native_forms import stage_form
            stage_form(engine,session,common,src['id'],tgt['id'],roots,form,proof)
            proof.append({'type':'outfit','source':src['id'],'target':tgt['id'],'variant':variant,'battle_identity_retained':True,'routes':edits})
            return
        for id in engine.rows['ActorVisualStatusConfig']['ActorVisualStatusConfig_VisualStatusType']:
            row=engine.row('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatusType',id)
            if tgt['id'] in (row.get('_AvailableItemID') or []):types.append(row)
        if len(types)!=1:raise ValueError('Native outfit form type is ambiguous')
        native=types[0];tid=common.alloc('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatusType');statuses={}
        rows=[engine.row('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatus',id) for id in engine.rows['ActorVisualStatusConfig']['ActorVisualStatusConfig_VisualStatus']]
        rows=[r for r in rows if r['_StatusType']==native['_ID']]
        rows.sort(key=lambda r:(r['_SortOrder'],r['_ID']))
        if type(form) is not int or not 0<=form<len(rows):raise ValueError('Form selection outside native status range')
        for row in rows:
            id=common.alloc('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatus');statuses[row['_ID']]=id
            common.patch('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatus',id,{'_StatusType':tid},template=row['_ID'])
        common.patch('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatusType',tid,{'_AvailableItemID':[src['id']],'_DefaultVisualStatusID':statuses[native['_DefaultVisualStatusID']] if form==0 else statuses[rows[form]['_ID']]},template=native['_ID'])
        changed=0
        for cab,root in roots:
            for pid,t in walk(cab,root):
                if 'visualStatusMap' not in t:continue
                for entry in t['visualStatusMap']:
                    old=entry['checkVisualStatusId'];canonical=old
                    if old not in statuses:
                        # The preserved base can already contain a reviewed
                        # local status-ID map. Resolve it by complete native
                        # row content, never by assuming a numeric offset.
                        try:existing=common.get('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatus',old)
                        except KeyError:continue
                        identity=lambda r:{k:v for k,v in r.items() if k not in ('_ID','_StatusType')}
                        matches=[r['_ID'] for r in rows if identity(r)==identity(existing)]
                        if len(matches)!=1:raise ValueError('Existing outfit form cannot be resolved to a unique native status')
                        canonical=matches[0]
                    if canonical in statuses:
                        entry['checkVisualStatusId']=statuses[canonical];changed+=1
                cab.put(pid,t)
        if not changed:raise ValueError('Outfit form controller is unresolved')
    proof.append({'type':'outfit','source':src['id'],'target':tgt['id'],'variant':variant,'battle_identity_retained':True,'routes':edits})
