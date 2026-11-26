"""Native visual-status form control without changing equipped identities."""
from advanced_recipes import walk

def stage_form(engine,session,common,source,target,roots,form,proof,shared_default=False):
    types=[engine.row('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatusType',id) for id in engine.rows['ActorVisualStatusConfig']['ActorVisualStatusConfig_VisualStatusType']]
    types=[r for r in types if target in (r['_AvailableItemID'] or [])]
    if len(types)!=1:raise ValueError('Native form type is ambiguous')
    native=types[0]
    rows=[engine.row('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatus',id) for id in engine.rows['ActorVisualStatusConfig']['ActorVisualStatusConfig_VisualStatus']]
    rows=[r for r in rows if r['_StatusType']==native['_ID']]
    rows.sort(key=lambda r:(r['_SortOrder'],r['_ID']))
    if type(form) is not int or not 0<=form<len(rows):raise ValueError('Native form index outside status range')
    if form==0 or shared_default:
        current=common.get('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatusType',native['_ID'])
        available=list(current['_AvailableItemID'] or [])
        if source not in available:available.append(source)
        default=native['_DefaultVisualStatusID'] if form==0 else rows[form]['_ID']
        common.patch('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatusType',native['_ID'],{'_AvailableItemID':available,'_DefaultVisualStatusID':default})
        proof.append({'type':'native_form_default','source':source,'target':target,'form':form,'default_status':default,'original_event_and_status_ids_retained':True,'shared_type_default':True})
        return
    tid=common.alloc('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatusType');mapping={}
    for row in rows:
        id=common.alloc('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatus');mapping[row['_ID']]=id
        common.patch('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatus',id,{'_StatusType':tid},template=row['_ID'])
    common.patch('ActorVisualStatusConfig','ActorVisualStatusConfig_VisualStatusType',tid,{'_AvailableItemID':[source],'_DefaultVisualStatusID':mapping[rows[form]['_ID']]},template=native['_ID'])
    count=0
    for cab,root in roots:
        for pid,t in walk(cab,root):
            if 'visualStatusMap' not in t:continue
            for entry in t['visualStatusMap']:
                old=entry['checkVisualStatusId']
                if old in mapping:entry['checkVisualStatusId']=mapping[old];count+=1
            cab.put(pid,t)
    if not count:raise ValueError('Native form controller is unresolved')
    proof.append({'type':'fixed_form','source':source,'target':target,'form':form,'controller_links':count})
