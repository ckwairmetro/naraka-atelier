"""Collect canonical rule trees for every numbered catalogue cosmetic."""
import gzip,json,sys,zipfile,hashlib
from pathlib import Path
ROOT=Path(__file__).parent;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from decode_appres import decode
from bundle_editor import digest_file
from naraka_extract import read_info,decompress_block
from UnityPy.files import SerializedFile
from UnityPy.streams import EndianBinaryReader
from native_rule_pin import pin_rule_config

def main():
    sys.stdout.reconfigure(encoding='utf8')
    res=ROOT/'resources';manifest=json.loads((res/'build.json').read_text(encoding='utf8'));game=Path(manifest['game'])
    index=decode(zipfile.ZipFile(res/'pristine_AppRes.info').read('data'));records={b['bundle_name']:b for b in index['bundles']};assets={a:b['bundle_name'] for b in index['bundles'] for a in b['assets']}
    filenames={}
    for path in assets:filenames.setdefault(Path(path).name,[]).append(path)
    data=zipfile.ZipFile(res/'catalogue.zip').read('naraka-catalogue/data.js').decode();catalog=json.loads(data[data.index('{'):data.rindex('}')+1]);items=[i for i in catalog['items'] if i.get('z')]
    cache=ROOT.parent/'work/canonical-rare-cabs';cache.mkdir(parents=True,exist_ok=True);out=res/'rare_rules';out.mkdir(exist_ok=True)
    grouped={};result={}
    for i in items:
        filename=i['z'].get('rule',{}).get('asset');paths=filenames.get(filename,[])
        if len(paths)!=1:result[str(i['id'])]={'error':'Rule resource ambiguous or absent'};continue
        path=paths[0];grouped.setdefault(assets[path],[]).append((i,path))
    for bundle,jobs in grouped.items():
        print('Canonical rules:',bundle,flush=True);expected=records[bundle]['file_hash']
        folder=cache/expected;folder.mkdir(exist_ok=True);marker=folder/'sha.txt';cached=[p for p in folder.glob('CAB-*') if not p.name.endswith('.resS')]
        trusted=len(cached)==1 and marker.exists() and digest_file(cached[0])==marker.read_text()
        if trusted:cabfile=cached[0]
        else:
            candidates=[game/bundle,ROOT.parent/'work/recovered-original-reference/StreamingAssets'/bundle,*ROOT.parent.glob('work/*-transaction/backups/*/'+bundle)]
            source=next((p for p in candidates if p.is_file() and digest_file(p,'md5')==expected),None)
            if source is None:raise ValueError('No canonical bundle matching installed-build index: '+bundle)
            info=read_info(str(source));node=info['nodes'][0];cabfile=folder/node[3]
            at=(4096+info['info_consumed']+4095)//4096*4096;logical=0
            with source.open('rb') as f,cabfile.open('wb') as outcab:
                for us,cs,co in info['blocks']:
                    if logical>=node[1]:break
                    f.seek(at);d=decompress_block(f.read(cs),us,co);outcab.write(d[:min(us,node[1]-logical)]);logical+=us;at=(at+cs+4095)//4096*4096
            marker.write_text(digest_file(cabfile))
        with cabfile.open('rb') as f:
            sf=SerializedFile(EndianBinaryReader(f),name=cabfile.name);ab=next(o.read_typetree() for o in sf.objects.values() if o.type.name=='AssetBundle');entries=dict(ab['m_Container'])
            for item,path in jobs:
                entry=entries[path]
                if entry['asset']['m_FileID']:raise ValueError('External canonical rule pointer')
                pid=entry['asset']['m_PathID'];tree=sf.objects[pid].read_typetree();slots=item['z']['slots'];n=tree['usedDigitCount']
                preview=(item['z'].get('previews') or [[s.get('init',0) for s in slots]])[-1];code=['0']*n
                for slot,v in zip(slots,preview):
                    a,b=slot['digitPos'];text=str(v).zfill(b-a+1)
                    if b>=n or len(text)!=b-a+1:raise ValueError('Catalogue digit layout disagrees with native rule')
                    code[a:b+1]=text
                code=''.join(code)
                try:_,proof=pin_rule_config(tree,code)
                except ValueError as exc:
                    bad=[]
                    for g in tree['ruleGroups']:
                        for rule in g['ruleDatas']:
                            a,b=rule['ruleIndexRange']['x'],rule['ruleIndexRange']['y'];value=int(code[a:b+1]);hits=[r for r in rule['subRules'] if r['subRuleStartNumber']<=value<=r['subRuleEndNumber']]
                            if len(hits)!=1:bad.append({'name':rule['ruleName'],'range':[a,b],'value':value,'bands':[[r['subRuleStartNumber'],r['subRuleEndNumber']] for r in rule['subRules']]})
                    result[str(item['id'])]={'bundle':bundle,'path':path,'path_id':pid,'width':n,'default_code':code,'error':str(exc),'bad':bad}
                    value={'item':item['id'],'bundle':bundle,'path':path,'path_id':pid,'tree':tree,'default_code':code,'canonical_md5':expected}
                    with gzip.open(out/(str(item['id'])+'.json.gz'),'wt',encoding='utf8') as z:json.dump(value,z)
                    print('Rule constraint requires investigation:',item['id'],code,bad[:2],flush=True);continue
                value={'item':item['id'],'bundle':bundle,'path':path,'path_id':pid,'tree':tree,'default_code':code,'canonical_md5':expected}
                with gzip.open(out/(str(item['id'])+'.json.gz'),'wt',encoding='utf8') as z:json.dump(value,z)
                result[str(item['id'])]={'bundle':bundle,'path':path,'path_id':pid,'width':n,'default_code':code,'rules':len(proof['rules'])}
    (res/'rare-index.json').write_text(json.dumps(result,indent=2),encoding='utf8');print('Indexed',len(result),'numbered items',flush=True)
if __name__=='__main__':main()
