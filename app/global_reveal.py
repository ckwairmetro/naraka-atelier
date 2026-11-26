"""Confirmed native cosmetic menu reveal, composable with appearance swaps."""
import copy,time
from pathlib import Path
from table_codec import section_rows,changed_rows

RULES={
 'outfit':('FashionConfig','FashionConfig_FashionBody','_ItemShowType',7),
 'weapon':('WeaponSkin','WeaponSkin_WeaponSkin','_ItemType',20),
 'hair':('HairItem','HairItem_Hair','_ItemShowType',30),
 'accessory':('OrnamentItem','OrnamentItem_OrnamentItem','_ItemShowType',9),
 'grapple':('OrnamentItem','OrnamentItem_OrnamentItem','_ItemShowType',9),
 'background':('ShowOffItemConfig','ShowOffItemConfig_BackGround','_ItemShowType',12),
 'platform':('ShowOffItemConfig','ShowOffItemConfig_PlatformItem','_ItemShowType',14),
 'pose':('ShowOffItemConfig','ShowOffItemConfig_ShowAction','_ItemShowType',15),
 'voice':('HeroVoice','HeroVoice_VoicePacket','_ItemShowType',43),
 'music':('HeroVoice','HeroVoice_BattleBackgroundMusic','_ItemShowType',51),
 'broadcast':('KillBroadcast','KillBroadcast_Skin','_ItemType',35),
 'lootpile':('InteractiveBuildSkin','InteractiveBuildSkin_InteractiveBuildSkin','_ItemType',36),
 'rescue':('RescueSkin','RescueSkin_RescueSkin','_ItemType',33),
}
FUTURE=1893456000


def stage_reveal(engine,common):
    e=engine;cab=common.cab
    for table in ('CommonItemCommercialConfig','CommonItemVisibleBlockConfig'):
        entries=[v for path,v in cab.entries().items() if Path(path).stem.lower()==table.lower()]
        if len(entries)!=1:raise ValueError('Ambiguous config table '+table)
        e.pids[table]=entries[0]['asset']['m_PathID']
    now=int(time.time());plans={};originals={};coverage={};commercial={};notes=[]
    def add(table,section,id,changes,category):
        old=common.get(table,section,id);actual={k:v for k,v in changes.items() if old[k]!=v}
        if not actual:return
        key=(table,section,id)
        if key in plans:raise ValueError('A row was assigned twice')
        originals.setdefault(table,common.table(table)[2]);plans[key]={'changes':actual,'before':{k:old[k] for k in actual},'category':category}
    for category,(table,section,field,reward) in RULES.items():
        items=[i for i in e.items.values() if i['c']==category and not i.get('synthetic')]
        _,_,rows=section_rows(common.table(table)[2],section)
        stats={'catalogue_records':len(items),'resolved_records':0,'visibility_flags':0,'future_release_dates':0,'expiry_entries':0,'regional_visibility_entries':0,'native_nonplayer_hair':[],'native_page_exclusions':[]}
        for item in items:
            id=item['id']
            if id not in rows:raise ValueError('Catalogue/native visibility join failed: '+item['key'])
            row=common.get(table,section,id);stats['resolved_records']+=1;commercial[(reward,id)]=category
            if row[field] not in (1,2):raise ValueError('Unreviewed visibility mode '+item['key'])
            changes={field:1}
            if row[field]!=1:stats['visibility_flags']+=1
            start=row.get('_StartTime')
            if start and start['_timestamp']>now:
                changes['_StartTime']={'_timestamp':0};stats['future_release_dates']+=1
            if category=='hair' and not row['_PlayerCanUse']:stats['native_nonplayer_hair'].append(id)
            if category=='voice' and not row['_ShowInCustomPage']:stats['native_page_exclusions'].append(id)
            add(table,section,id,changes,category)
        coverage[category]=stats
    # Hair-effect colour rewards are native options rather than separate main
    # catalogue cards. Preserve their effect/hair associations and ownership.
    table='HairEffect';section='HairEffect_EffectReward';_,_,rows=section_rows(common.table(table)[2],section)
    coverage['hair_effect_reward']={'native_records':len(rows),'visibility_flags':0,'future_release_dates':0,'expiry_entries':0,'regional_visibility_entries':0}
    for id in rows:
        row=common.get(table,section,id)
        if row['_ItemShowType'] not in (1,2):raise ValueError('Unreviewed hair effect reward mode')
        changes={'_ItemShowType':1};commercial[(61,id)]='hair_effect_reward'
        if row['_ItemShowType']!=1:coverage['hair_effect_reward']['visibility_flags']+=1
        if row.get('_StartTime') and row['_StartTime']['_timestamp']>now:
            changes['_StartTime']={'_timestamp':0};coverage['hair_effect_reward']['future_release_dates']+=1
        add(table,section,id,changes,'hair_effect_reward')
    table='CommonItemCommercialConfig';section=table+'_OffShelvesConfig';_,_,rows=section_rows(common.table(table)[2],section)
    for id in rows:
        row=common.get(table,section,id);category=commercial.get((row['_ItemType'],row['_ItemId']))
        if category and row['_EndTime'] and row['_EndTime']['_timestamp']<FUTURE:
            add(table,section,id,{'_EndTime':{'_timestamp':FUTURE}},category);coverage[category]['expiry_entries']+=1
    table='CommonItemVisibleBlockConfig';section=table+'_BlockConfig';_,_,rows=section_rows(common.table(table)[2],section)
    for id in rows:
        row=common.get(table,section,id);category=commercial.get((row['_ItemType'],row['_ItemId']))
        if category and row['_BlockServerList']:
            # Native Misc.CheckServerList(empty) returns false. This changes
            # the local catalogue filter only; native page associations remain.
            add(table,section,id,{'_BlockServerList':[]},category);coverage[category]['regional_visibility_entries']+=1
    # Fixed-size scalar rows can be patched together without rebuilding their
    # entire table for every item. Resized array rows use the existing encoder.
    resized=[]
    for table in originals:
        data=common.table(table)[2];out=bytearray(data);positions={}
        for (t,section,id),plan in plans.items():
            if t!=table:continue
            if section not in positions:
                _,rs,raws=section_rows(data,section);positions[section]=({row['id']:row for row in rs},raws)
            offsets,raws=positions[section];value=common.decoder.row(section,raws[id]);value.update(copy.deepcopy(plan['changes']));encoded=common.encoder.row(section,value)
            if len(encoded)!=len(raws[id]):resized.append((table,section,id,plan));continue
            offset=offsets[id]['offset'];out[offset:offset+len(encoded)]=encoded
            common.proof.append({'table':table,'section':section,'id':id,'added':False,'fields':list(plan['changes']),'prototype':None})
        common.tables[table][2]=bytes(out)
    for table,section,id,plan in resized:common.patch(table,section,id,plan['changes'])
    for table,before in originals.items():
        after=common.table(table)[2];delta=changed_rows(before,after)
        expected={(section,id) for t,section,id in plans if t==table}
        if set(delta)!=expected:raise ValueError('Native row scope differs: '+table)
        for section in {section for section,id in delta}:
            _,_,a=section_rows(before,section);_,_,b=section_rows(after,section)
            for sec,id in delta:
                if sec!=section:continue
                old=common.decoder.row(section,a[id]);new=common.decoder.row(section,b[id]);actual={k for k in old if old[k]!=new[k]}
                if actual!=set(plans[(table,section,id)]['changes']):raise ValueError('Native field scope differs')
    # Effects contain no generic owned-only visibility field. Their existing
    # collectors and owner/hero/weapon/type lists are deliberately not expanded.
    for category in ('skill','effect'):
        ls=[i for i in e.items.values() if i['c']==category and not i.get('synthetic')]
        coverage[category]={'catalogue_records':len(ls),'policy':'Preserve native effect groups, owners, ability slots, weapon families and copy/model restrictions; reveal parent item definitions. Native panel accessibility requires live check.','direct_effect_definition_changes':0}
    return {'type':'global_cosmetic_reveal','coverage':coverage,'changed_rows':len(plans),'scope_validated':True,'page_associations_preserved':True,'ownership_unchanged':True,'plan':[dict(table=t,section=s,id=id,**v) for (t,s,id),v in plans.items()]}
