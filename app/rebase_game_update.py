"""Rebind the application's native resources to an updated, verified-pristine game build.

Run only with Naraka and its launcher closed, after the full AppRes integrity check passes.
Reads the game; writes only app/resources (back it up first). Usage:
    python rebase_game_update.py --catalogue "D:/Naraka Models/export/naraka-catalogue.zip" --label "2026-11-18 Steam build 26771036"
"""
import argparse,base64,datetime,gzip,hashlib,json,shutil,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path[:0]=[str(ROOT/'vendor'),str(ROOT)]
from build_body_alias_candidate import unpack_logical,load_sf
from decode_appres import decode
from table_codec import load_table
import game_tables
from body_alias_trial import sha_file,ensure_closed
from bundle_editor import digest_file

RES=ROOT/'resources';COMMON='f/a/fab72152d7112058';ARCHIVE='e/5/e50ef81ba77ae51a';PALETTE='7/1/71935da643983428'

def main():
    p=argparse.ArgumentParser();p.add_argument('--catalogue',type=Path,required=True);p.add_argument('--label',required=True);a=p.parse_args()
    ensure_closed()
    manifest=json.loads((RES/'build.json').read_text(encoding='utf8'));game=Path(manifest['game']);root=game.parent.parent
    index=decode(zipfile.ZipFile(game/'AppRes.info').read('data'));records={b['bundle_name']:b for b in index['bundles']}
    # Every bundle the app reads or tracks must be the verified pristine bytes of the new build.
    tracked=sorted(set(manifest['initial_installed'])-{'AppRes.info'}|{COMMON,ARCHIVE,PALETTE})
    for rel in tracked:
        r=records[rel];f=game/rel
        if f.stat().st_size!=r['file_size'] or digest_file(f,'md5')!=r['file_hash']:raise ValueError('Not pristine for the installed index: '+rel)
    report={'label':a.label,'prepared':datetime.datetime.now().isoformat(timespec='seconds'),'game_files_modified':False}

    # 1. Packaged baselines and pristine index.
    for rel in ('AppRes.info',COMMON,ARCHIVE):
        dest=RES/'baseline'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(game/rel,dest)
    shutil.copy2(game/'AppRes.info',RES/'pristine_AppRes.info')

    # 2. Fingerprints: executables/version files and tracked resources.
    old_critical=dict(manifest['critical'])
    manifest['critical']={rel:sha_file(root/rel) for rel in manifest['critical']}
    manifest['initial_installed']={rel:sha_file(game/rel) for rel in manifest['initial_installed']}
    for rel,h in manifest['initial_installed'].items():
        if sha_file(RES/'baseline'/rel if (RES/'baseline'/rel).exists() else game/rel)!=h:raise ValueError('Baseline copy differs: '+rel)
    manifest['recorded_date']=datetime.date.today().isoformat();manifest['base_profile']='Verified pristine build '+a.label+'; no inherited substitutions'
    manifest.setdefault('rebase_history',[]).append({'date':manifest['recorded_date'],'label':a.label,'previous_critical':old_critical})
    report['critical_changed']=[k for k in old_critical if old_critical[k]!=manifest['critical'][k]]

    # 3. Native rows for every table/section the engine already uses.
    with gzip.open(RES/'native_rows.json.gz','rt',encoding='utf8') as f:old=json.load(f)
    raw,_=unpack_logical(game/COMMON);sf=load_sf(raw)
    container=dict(next(o.read_typetree() for o in sf.objects.values() if o.type.name=='AssetBundle')['m_Container'])
    new={'pids':{},'tables':{}};diff={}
    for name,sections in old['tables'].items():
        entry=next(v for k,v in container.items() if Path(k).stem.lower()==name.lower());pid=entry['asset']['m_PathID']
        _,_,data=load_table(sf,pid,name);new['pids'][name]=pid;new['tables'][name]={}
        found={s['name']:s for s in game_tables.sections(data) if s['offset']}
        for sec in sections:
            if sec not in found:raise ValueError('Section disappeared: '+sec)
            rows=game_tables.rows(data,found[sec])
            if rows and rows[0]['keyType']!='uint32':raise ValueError('Section key type changed: '+sec)
            new['tables'][name][sec]={str(r['id']):base64.b64encode(data[r['offset']:r['offset']+r['size']]).decode() for r in rows}
            o,n=old['tables'][name][sec],new['tables'][name][sec]
            d={'added':len(set(n)-set(o)),'removed':len(set(o)-set(n)),'changed':sum(1 for k in set(o)&set(n) if o[k]!=n[k])}
            if any(d.values()):diff[sec]=d
    with gzip.open(RES/'native_rows.json.gz','wt',encoding='utf8') as f:json.dump(new,f)
    report['native_row_changes']=diff

    # 4. Generalized outfit/hair routes from the refreshed research inventory.
    outfits={};hairs={}
    def route(r):return {k:r[k] for k in ('path','bundle') if k in r}
    for line in open('D:/Naraka Models/data/game-research/out/cosmetics.jsonl',encoding='utf8'):
        r=json.loads(line);id=str(r['cosmeticId'])
        if r['category']=='outfit':
            temps=[]
            for t in r.get('actorTemps',[]):
                parts=[{'id':v['visualPartId'],'battle':route(v.get('battle',{})),'wardrobe':route(v.get('wardrobe',{}))} for v in t.get('visualParts',[]) if v.get('bodyVisualPart')==0]
                temps.append({'id':t['actorTempId'],'body_size':t.get('bodySize',{}).get('bodySizeId'),'parts':parts})
            outfits[id]={'temps':temps,'placeholder':r.get('placeholder',False)}
        elif r['category']=='hair':
            hairs[id]={'visuals':[{'id':h['hairVisualId'],'cosmetic':h.get('cosmeticKey'),'prefabs':[route(q) for q in h.get('inferredPrefabs',[]) if q.get('path')]} for h in r.get('hairConfigs',[])]}
    with gzip.open(RES/'generalized.json.gz','rt',encoding='utf8') as f:prev=json.load(f)
    report['generalized']={'outfits':[len(prev['outfits']),len(outfits)],'hairs':[len(prev['hairs']),len(hairs)],
        'outfit_routes_changed':sum(1 for k in set(prev['outfits'])&set(outfits) if prev['outfits'][k]!=outfits[k]),
        'hair_routes_changed':sum(1 for k in set(prev['hairs'])&set(hairs) if prev['hairs'][k]!=hairs[k])}
    with gzip.open(RES/'generalized.json.gz','wt',encoding='utf8') as f:json.dump({'outfits':outfits,'hairs':hairs,'canonical_archive_sha256':sha_file(game/ARCHIVE)},f)

    # 5. Shared protobuf archives used by effect recipes.
    raw,_=unpack_logical(game/ARCHIVE);sf=load_sf(raw);report['archives']={}
    for asset in ('proto_track_archive','hero_skill_effect_archive'):
        obj=next(o for o in sf.objects.values() if o.type.name=='TextAsset' and o.read_typetree()['m_Name']==asset)
        data=obj.read_typetree()['m_Script'].encode('utf8',errors='surrogateescape')
        with gzip.open(RES/(asset+'.bin.gz'),'rb') as f:report['archives'][asset]='unchanged' if f.read()==data else 'changed'
        with gzip.open(RES/(asset+'.bin.gz'),'wb') as f:f.write(data)

    # 6. Native hair palette.
    raw,_=unpack_logical(game/PALETTE);sf=load_sf(raw)
    en=dict(next(o.read_typetree() for o in sf.objects.values() if o.type.name=='AssetBundle')['m_Container'])
    group=sf.objects[next(v for k,v in en.items() if '/group_data/' in k)['asset']['m_PathID']].read_typetree()
    colors=[sf.objects[q['m_PathID']].read_typetree()['MyData'] for q in group['CustomColorCandidates']]
    report['palette']='unchanged' if json.loads((RES/'palette.json').read_text())==colors else 'changed'
    (RES/'palette.json').write_text(json.dumps(colors),encoding='utf8')

    # 7. Catalogue for the same client.
    shutil.copyfile(a.catalogue,RES/'catalogue.zip')
    (RES/'build.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    out=ROOT.parent/'reports'/('rebase-'+manifest['recorded_date']+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=1)[:4000])

if __name__=='__main__':main()
