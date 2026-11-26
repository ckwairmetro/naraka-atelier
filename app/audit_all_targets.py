"""Record a compatible source and control schema for every catalogue target."""
import json
from collections import defaultdict
from pathlib import Path
from full_engine import FullEngine
from core import save_json
ROOT=Path('D:/naraka_unlocker')
def main():
    e=FullEngine(ROOT/'work/atelier-pristine-qa');pools=defaultdict(list)
    for i in e.items.values():pools[i['c']].append(i)
    for v in pools.values():v.sort(key=lambda i:(not i.get('synthetic'),i.get('q',1),str(i['id'])))
    cases=[];errors=[]
    for target in e.items.values():
        if target.get('synthetic'):continue
        category=target['kind'] if target['c']=='effect' else 'outfit' if target['c']=='skill' else target['c']
        found=None
        for source in pools[category]:
            heroes=set(source.get('h',[]))&set(target.get('h',[]))
            if target['c']=='skill' and not heroes:continue
            hero=next(iter(heroes),next(iter(source.get('h',[]) or target.get('h',[])),None))
            if e.compatible(source,target,hero):continue
            s={'source':source['key'],'target':target['key'],'hero':hero}
            try:
                e.validate([s]);controls=e.controls(target['key'])
            except (ValueError,KeyError) as exc:continue
            found={'selection':s,'controls':len(controls)};break
        if found:cases.append(found)
        else:errors.append({'target':target['key'],'category':target['c'],'reason':'No individually compatible source found; may require a model/effect combination'})
    result={'targets':len(cases)+len(errors),'individually_validated':len(cases),'unresolved':errors,'cases':cases,'game_files_modified':False}
    save_json(ROOT/'reports/catalogue-target-audit-v2.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='cases'}),flush=True)
if __name__=='__main__':main()
