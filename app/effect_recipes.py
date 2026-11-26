"""Clone only native particle/sound presentation selectors; preserve gameplay events."""
import collections,hashlib,gzip
from proto_codec import fields,vint,delimited

def compile_effects(engine,session,common,selections,proof):
    # Rebuild from canonical archives so changing a slot removes the previous
    # fixture's source-scoped branch rather than silently stacking both.
    import json
    base_file=engine.resources/'base-effects.json'
    if base_file.exists():
        base=json.loads(base_file.read_text());weapon={tuple(x[:2]):x[2] for x in base['weapon']};skills={tuple(x[:2]):x[2] for x in base['skill']}
    else:
        weapon={(2311500,20032):10043,(2311500,20005):10005}
        skills={(3400100,10056):10056,(3400100,10057):10057}
    models={int(engine.items[s['source']]['id']):int(engine.items[s['target']]['id']) for s in selections if engine.items[s['target']]['c']=='weapon'}
    changed=False
    for s in selections:
        src,tgt=engine.items[s['source']],engine.items[s['target']]
        if tgt['c']=='effect' and tgt['kind']=='weapon':
            weapon[(int(src['id']),tgt['type'])]=int(str(tgt['id'])[1:]);changed=True
        elif tgt['c']=='skill':
            id=int(tgt['id']);groups=engine.skill_groups.get(id,[])
            talent=engine.skill_scope(id)
            for key,g in list(skills.items()):
                members=engine.row('SkillEffectCustom','SkillEffectCustom_SkillEffectGroup',g)['_SkillEffects'] or []
                if key[0]==int(src['id']) and any(engine.skill_scope(m)==talent for m in members):del skills[key]
            for g in groups:skills[(int(src['id']),g)]=g
            changed=True
    if not changed and 2311500 not in models:return
    gate_map=collections.defaultdict(list);guards={}
    def guard(kind,source):
        key=(kind,source)
        if key not in guards:
            prototype=3603366 if kind=='weapon' else 3602298
            id=common.alloc('BattleAction','BattleAction_Action')
            common.patch('BattleAction','BattleAction_Action',id,{'_ActionIntListParams':[source]},template=prototype)
            guards[key]=id
        return guards[key]
    actions=[engine.row('BattleAction','BattleAction_Action',i) for i in engine.rows['BattleAction']['BattleAction_Action']]
    for (source,slot),effect in weapon.items():
        row=engine.row('WeaponSkin','WeaponSkin_SkinBattleEffect',effect);suitable=row['_SuitableWeaponSkin']
        if not engine.effect_fits_weapon(engine.effective_weapon('weapon:'+str(source),selections),effect):continue
        selected=[]
        for a in actions:
            if a['_ActionLogicId']==3631149 and a['_ActionIntParams']==effect:selected.append(a['_ID'])
        if not selected and row['_EffectName']!='无':
            owners={i for i in engine.rows['WeaponSkin']['WeaponSkin_WeaponSkin'] if effect in (engine.row('WeaponSkin','WeaponSkin_WeaponSkin',i)['_SkinEffectIDs'] or [])}
            selected=[a['_ID'] for a in actions if a['_ActionLogicId']==3631192 and owners&set(a['_ActionIntListParams'] or [])]
        for id in selected:gate_map[id].append(guard('weapon',source))
    for (source,_),group in skills.items():
        native_group=engine.row('SkillEffectCustom','SkillEffectCustom_SkillEffectGroup',group)
        # Some ultimate looks replace a complete transformed actor (Vajra or
        # Mech), rather than adding particle branches. Reuse the native model
        # substitution route; the skill/gameplay timeline remains unchanged.
        for spec in native_group['_SkillCustomData'] or []:
            if spec[0]!=1 or len(spec)!=2:continue
            target=spec[1];info=engine.general['outfits'].get(str(target))
            if not info or not info['temps']:raise ValueError('Transformed actor native outfit is unresolved')
            family=info['temps'][0]['body_size'];default={90004:3400600,90007:3401800}.get(family)
            if default is None:continue
            if not any(a['_ActionLogicId']==3631226 and a['_ActionIntParams']==1 and group in (a['_ActionIntListParams'] or []) for a in actions):
                from outfit_recipes import outfit
                hero=int(next(s['hero'] for s in selections if engine.items[s['target']]['c']=='skill' and group in engine.skill_groups[int(engine.items[s['target']]['id'])]))
                keys=[f'outfit:{i}' for i in (default,target)];old={k:engine.items.get(k) for k in keys}
                try:
                    for key,id in zip(keys,(default,target)):engine.items[key]={'key':key,'id':id,'c':'outfit','h':[hero]}
                    outfit(engine,session,common,{'source':keys[0],'target':keys[1],'hero':hero},proof)
                finally:
                    for k,v in old.items():
                        if v is None:engine.items.pop(k,None)
                        else:engine.items[k]=v
        for a in actions:
            if a['_ActionLogicId']==3631226 and a['_ActionIntParams']==1 and group in (a['_ActionIntListParams'] or []):
                gate_map[a['_ID']].append(guard('outfit',source))
    gate_map={k:sorted(set(v)) for k,v in gate_map.items()}
    for name in ('proto_track_archive','hero_skill_effect_archive'):
        with gzip.open(engine.resources/(name+'.bin.gz'),'rb') as f:raw=f.read()
        if name=='proto_track_archive':new,detail=patch_tracks(raw,gate_map)
        else:
            out=[];count=0
            for f in fields(raw):
                if f['number']!=2:out.append(f['raw']);continue
                row=fields(f['value']);adds=[]
                for r in row:
                    if r['number']!=2:continue
                    cf=fields(r['value']);action=only(cf,1)
                    for g in gate_map.get(action,[]):
                        data=b''.join(scalar(1,g) if x['number']==1 else x['raw'] for x in cf)
                        adds.append(delimited(2,data));count+=1
                data=b''.join(x['raw'] for x in row if x['number']==1)+b''.join(adds)+b''.join(x['raw'] for x in row if x['number']!=1)
                out.append(delimited(f['number'],data) if adds else f['raw'])
            new=b''.join(out);detail={'added_keys':count}
        path='assets/raw_resources/proto_bytes/'+name+'.bytes'
        if path not in session.assets:
            hits=[p for p in session.assets if p.endswith('/'+name+'.bytes')]
            if len(hits)!=1:raise ValueError('Presentation archive path is ambiguous')
            path=hits[0]
        _,cab,en=session.asset(path);t=cab.tree(en['asset']['m_PathID']);t['m_Script']=new.decode('utf8',errors='surrogateescape');cab.put(en['asset']['m_PathID'],t)
        proof.append({'type':name,'source_guards':len(guards),'detail':detail})

def scalar(n,v):return vint(n<<3)+vint(v)
def only(fs,n):
    values=[f['value'] for f in fs if f['number']==n]
    if len(values)!=1:raise ValueError('Ambiguous protobuf field')
    return values[0]

def augment_conditions(data,entry_field,label,changes,gates):
    copies=[]
    for f in fields(data):
        if f['number']!=entry_field or f['wire']!=2:continue
        cf=fields(f['value']);checks=[x['value'] for x in cf if x['number']==2]
        hits=[x for x in checks if x in gates]
        if not hits:continue
        if len(hits)!=1:raise ValueError('Multiple requested cosmetic selectors require an explicit combined condition')
        gate=hits[0]
        for guard in gates[gate]:
            new=b''.join(scalar(2,guard) if x['number']==2 and x['value']==gate else x['raw'] for x in cf)
            assert [x['raw'] for x in cf if x['number']!=2]==[x['raw'] for x in fields(new) if x['number']!=2]
            copies.append(delimited(entry_field,new));changes.append({'track':label,'old_cosmetic_selector':gate,'new_source_guard':guard})
    return b''.join(copies)+data

def patch_tracks(raw,gates):
    changes=[];changed=[];original=fields(raw);chunks=[]
    for f in original:
        if f['number']!=1 or f['wire']!=2:chunks.append(f['raw']);continue
        row=fields(f['value']);name=only(row,1).decode();rows=[]
        for tr in row:
            if tr['number']!=2 or tr['wire']!=2:rows.append(tr['raw']);continue
            events=[]
            for ev in fields(tr['value']):
                if ev['number']!=1 or ev['wire']!=2:events.append(ev['raw']);continue
                evfields=[]
                for p in fields(ev['value']):
                    if p['number']!=3 or p['wire']!=2:evfields.append(p['raw']);continue
                    ps=[]
                    for typ in fields(p['value']):
                        if typ['wire']==2 and typ['number'] in (225,227):
                            new=augment_conditions(typ['value'],2 if typ['number']==225 else 4,name,changes,gates)
                            ps.append(typ['raw'] if new==typ['value'] else delimited(typ['number'],new))
                        else:ps.append(typ['raw'])
                    np=b''.join(ps);evfields.append(p['raw'] if np==p['value'] else delimited(p['number'],np))
                ne=b''.join(evfields);events.append(ev['raw'] if ne==ev['value'] else delimited(ev['number'],ne))
            nt=b''.join(events);rows.append(tr['raw'] if nt==tr['value'] else delimited(tr['number'],nt))
        nr=b''.join(rows)
        if nr!=f['value']:changed.append(name)
        chunks.append(f['raw'] if nr==f['value'] else delimited(f['number'],nr))
    result=b''.join(chunks)
    assert len(fields(result))==len(original)
    return result,{'changed_tracks':changed,'added_native_presentation_branches':changes,
        'selectors':dict(collections.Counter(x['old_cosmetic_selector'] for x in changes)),
        'all_original_branches_and_nonpresentation_events_preserved':True}
