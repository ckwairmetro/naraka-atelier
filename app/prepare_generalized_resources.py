"""Refresh canonical native metadata for the generalized application adapters."""
import base64,copy,gzip,json,shutil,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path[:0]=[str(ROOT/'vendor'),str(ROOT),'D:/naraka_unlocker/experiments']
from build_body_alias_candidate import unpack_logical,load_sf
from decode_appres import decode
from table_codec import load_table,section_rows
import game_tables
from body_alias_trial import sha_file
from bundle_editor import digest_file

def main():
    res=ROOT/'resources';original=Path('D:/naraka_unlocker/work/recovered-original-reference/StreamingAssets');common='f/a/fab72152d7112058'
    with gzip.open(res/'native_rows.json.gz','rt',encoding='utf8') as f:n=json.load(f)
    if not (res/'native_rows.v01.json.gz').exists():shutil.copy2(res/'native_rows.json.gz',res/'native_rows.v01.json.gz')
    raw,_=unpack_logical(original/common);sf=load_sf(raw);en=dict(next(o.read_typetree() for o in sf.objects.values() if o.type.name=='AssetBundle')['m_Container'])
    for name in ['CharacterConfig','ActorVisualStatusConfig','BattleAction','HeroVoice','SkillEffectCustom','HairEffect','HairHighlightDyeing','RareSkin']:
        p=next(v for p,v in en.items() if Path(p).stem.lower()==name.lower());pid=p['asset']['m_PathID'];_,_,data=load_table(sf,pid,name);n['pids'][name]=pid;n['tables'][name]={}
        for sec in game_tables.sections(data):
            if not sec['offset']:continue
            rows=game_tables.rows(data,sec)
            if not rows or rows[0]['keyType']!='uint32':continue
            n['tables'][name][sec['name']]={str(r['id']):base64.b64encode(data[r['offset']:r['offset']+r['size']]).decode() for r in rows}
    with gzip.open(res/'native_rows.json.gz','wt',encoding='utf8') as f:json.dump(n,f)
    # The corrected full research inventory provides exact AppRes ownership and
    # prefab/container evidence. Retain only native route descriptors here.
    outfits={};hairs={}
    def route(r):return {k:r[k] for k in ('path','bundle') if k in r}
    for l in open('D:/Naraka Models/data/game-research/out/cosmetics.jsonl',encoding='utf8'):
        r=json.loads(l);id=str(r['cosmeticId'])
        if r['category']=='outfit':
            temps=[]
            for t in r.get('actorTemps',[]):
                parts=[]
                for v in t.get('visualParts',[]):
                    if v.get('bodyVisualPart')!=0:continue
                    parts.append({'id':v['visualPartId'],'battle':route(v.get('battle',{})),'wardrobe':route(v.get('wardrobe',{}))})
                temps.append({'id':t['actorTempId'],'body_size':t.get('bodySize',{}).get('bodySizeId'),'parts':parts})
            outfits[id]={'temps':temps,'placeholder':r.get('placeholder',False)}
        elif r['category']=='hair':
            visuals=[]
            for h in r.get('hairConfigs',[]):
                visuals.append({'id':h['hairVisualId'],'cosmetic':h.get('cosmeticKey'),'prefabs':[route(p) for p in h.get('inferredPrefabs',[]) if p.get('path')]})
            hairs[id]={'visuals':visuals}
    # Snapshot the current installed base of the shared archive and audio data;
    # specialized v0.1 recipes remain the base of the generalized overlay.
    manifest=json.loads((res/'build.json').read_text(encoding='utf8'));game=Path(manifest['game'])
    for rel in ['e/5/e50ef81ba77ae51a']:
        assert sha_file(game/rel)==manifest['initial_installed'][rel]
        dest=res/'baseline'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(game/rel,dest)
    pristine_index=original/'AppRes.info'
    if not pristine_index.exists():
        pristine_index=Path('D:/naraka_unlocker/work/mass-weapons-matari-transaction/backups/2dbc3b90e98441e8accd1079e4251566/AppRes.info')
    index=decode(zipfile.ZipFile(pristine_index).read('data'));shutil.copy2(pristine_index,res/'pristine_AppRes.info')
    canonical={b['bundle_name']:b for b in index['bundles']}
    archive='e/5/e50ef81ba77ae51a'
    choices=[original/archive,game/archive,*Path('D:/naraka_unlocker/work').glob('*-transaction/backups/*/'+archive)]
    source=next((p for p in choices if p.is_file() and digest_file(p,'md5')==canonical[archive]['file_hash']),None)
    if not source:raise ValueError('No verified canonical archive')
    raw,_=unpack_logical(source);sf=load_sf(raw)
    for asset in ['proto_track_archive','hero_skill_effect_archive']:
        obj=next(o for o in sf.objects.values() if o.type.name=='TextAsset' and o.read_typetree()['m_Name']==asset)
        data=obj.read_typetree()['m_Script'].encode('utf8',errors='surrogateescape')
        with gzip.open(res/(asset+'.bin.gz'),'wb') as f:f.write(data)
    with gzip.open(res/'generalized.json.gz','wt',encoding='utf8') as f:json.dump({'outfits':outfits,'hairs':hairs,'canonical_archive_sha256':sha_file(source)},f)
    # Keep native palette payloads, including all lighting/finish properties.
    raw,_=unpack_logical(game/'7/1/71935da643983428');sf=load_sf(raw)
    en=dict(next(o.read_typetree() for o in sf.objects.values() if o.type.name=='AssetBundle')['m_Container'])
    group=sf.objects[next(v for p,v in en.items() if '/group_data/' in p)['asset']['m_PathID']].read_typetree()
    colors=[sf.objects[p['m_PathID']].read_typetree()['MyData'] for p in group['CustomColorCandidates']]
    (res/'palette.json').write_text(json.dumps(colors),encoding='utf8')
    print(json.dumps({'outfits':len(outfits),'hair':len(hairs),'palette':len(colors),'native_tables':len(n['tables'])}))
if __name__=='__main__':main()
