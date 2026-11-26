"""Round 3 controller: build on copies, inspect, install, status or restore."""
import argparse,gzip,json,sys,zipfile
from pathlib import Path
from core import Engine,COMMON,save_json,sha_file,Trial,ensure_closed
from native_edit import Session,CommonEditor
from canonical_outfit import stage_outfit
from bundle_editor import CabEditor
from decode_appres import decode

ROOT=Path('D:/naraka_unlocker')
STATE=ROOT/'work/atelier-round3'
REPORT=ROOT/'reports/atelier-round3.json'

def audit(r):
    layout=Path(r['candidate']);resource=Path(__file__).parent/'resources'
    with gzip.open(resource/'native_rows.json.gz','rt',encoding='utf8') as f:pids=json.load(f)['pids']
    common=r['packing'][COMMON]['objects']
    changed=[pid for node in common.values() for pid in node['objects']]
    if changed!=[pids['FashionConfig']]:raise ValueError('Unexpected common object changes: '+str(changed))
    # Read the independently verified packed CAB, not a staged config object.
    name=next(iter(common));cab=CabEditor(layout/'packing'/Path(COMMON).name/name)
    original=CabEditor(STATE/'decoded-cache'/r['all_eight_base_hashes'][COMMON]/name)
    try:
        for pid,obj in original.sf.objects.items():
            if pid!=pids['FashionConfig'] and obj.get_raw_data()!=cab.sf.objects[pid].get_raw_data():
                raise ValueError('Unrelated common table changed')
    finally:cab.close();original.close()
    def read_index(path):
        with zipfile.ZipFile(path) as z:return decode(z.read('data'))
    before=read_index(resource/'baseline/AppRes.info');after=read_index(layout/'AppRes.info')
    for a,b in zip(before['bundles'],after['bundles'],strict=True):
        changes={k for k in a if a[k]!=b[k]}
        if not changes<={'file_hash','file_size','crc'}:raise ValueError('Index ownership/dependency changes: '+str(changes))
    before['bundles']=after['bundles']
    if before!=after:raise ValueError('Non-bundle index metadata changed')
    for rel,h in r['candidate_hashes'].items():
        if sha_file(layout/rel)!=h:raise ValueError('Candidate hash changed: '+rel)
    for rel,detail in r['packing'].items():
        if not detail.get('node_streams_verified'):raise ValueError('Packed node verification missing: '+rel)
    r['scope_audit']={'passed':True,'all_common_objects_except_fashion_identical':True,
                      'character_config_raw_object_identical':True,'no_index_asset_or_dependency_changes':True,
                      'all_packed_node_streams_verified':True}
    save_json(REPORT,r)

def main():
    sys.stdout.reconfigure(encoding='utf8')
    p=argparse.ArgumentParser();p.add_argument('action',choices=['build','audit','apply','restore','status']);a=p.parse_args()
    if a.action=='build':
        e=Engine(STATE);status=e.check_build(strict=True)
        if not status['ok']:raise ValueError(status['errors'])
        with gzip.open(e.resources/'generalized.json.gz','rt',encoding='utf8') as f:inventory=json.load(f)
        layout,_=e.build([]);session=Session(e,layout)
        common=CommonEditor(e,session.edit(COMMON).cab())
        proof=stage_outfit(e,session,common,inventory,3400100,3400117,1000004)
        # Replay the historical accepted same-bundle fixture's structural edits.
        legacy=json.loads((ROOT/'reports/matari-native-prefab-context-candidate.json').read_text())
        assert proof['target_entry']==legacy['root']['new_container_entry']
        assert proof['target_root_id']==legacy['root']['target_root_id']
        assert proof['target_root_changed_fields']==legacy['root']['target_root_changed_fields']==['m_Name']
        assert proof['binding_keys']==sorted(x['source_context_key'] for x in legacy['translated_binding_rows'])
        proof['historical_accepted_fixture_structure_reproduced']=True
        common.flush();hashes=session.finish(print)
        if not e.check_build(strict=True)['ok']:raise ValueError('Installed inputs changed during compilation')
        changed={p:h for p,h in hashes.items() if h!=e.manifest['initial_installed'][p]}
        original={p:e.manifest['initial_installed'][p] for p in changed}
        report={'round':3,'status':'candidate_validated_not_installed','candidate':str(layout),'transaction':str(STATE/'transaction'),
                'game':str(e.game),'originals':original,'candidate_hashes':changed,'all_eight_base_hashes':e.manifest['initial_installed'],
                'proof':proof,'packing':session.proofs,'native_rows':common.proof,'native_result':'pending',
                'limitations':['Same-bundle, same-hero, one-main-part outfits only','Shared source template recolours can share the changed model','Split UI/battle and cross-bundle pairs remain blocked']}
        save_json(REPORT,report);print(json.dumps({k:v for k,v in report.items() if k!='packing'},ensure_ascii=False,indent=2))
        return
    r=json.loads(REPORT.read_text(encoding='utf8'))
    if a.action=='audit':audit(r);print(json.dumps(r['scope_audit']));return
    trial=Trial(Path(r['game']),Path(r['candidate']),Path(r['transaction']),r['originals'],r['candidate_hashes'])
    if a.action=='apply':
        audit(r)
        ensure_closed()
        for rel,h in r['all_eight_base_hashes'].items():
            if sha_file(Path(r['game'])/rel)!=h:raise ValueError('Pre-test resource differs: '+rel)
        result=trial.apply();r['status']='installed_native_result_pending';r['installation']=result
        expected=r['all_eight_base_hashes']|r['candidate_hashes']
        assert all(sha_file(Path(r['game'])/p)==h for p,h in expected.items())
        r['all_eight_installed_hashes_verified']=True
        save_json(REPORT,r);print(json.dumps({'status':r['status'],'files':len(r['candidate_hashes']),'backup':result['transaction']['backup_id'],'all_eight_verified':True}))
    elif a.action=='restore':
        trial.restore();assert all(sha_file(Path(r['game'])/p)==h for p,h in r['all_eight_base_hashes'].items())
        r['status']='restored';save_json(REPORT,r);print('All eight pre-test hashes restored.')
    else:print(json.dumps(trial.status(),indent=2))

if __name__=='__main__':main()
