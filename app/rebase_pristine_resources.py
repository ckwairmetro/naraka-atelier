"""Bind the application to the verified clean installation, not an old mod stack."""
import json,shutil
from pathlib import Path
from core import sha_file,save_json,ensure_closed

ROOT=Path('D:/naraka_unlocker');RES=ROOT/'app/resources'
def main():
    ensure_closed();report=json.loads((ROOT/'reports/clean-reset-2026-11-14.json').read_text())
    if not report['restored']:raise ValueError('Clean resource restoration is not complete')
    old=json.loads((RES/'build.json').read_text());game=Path(old['game'])
    backup=ROOT/'work/accepted-mod-base-resources-2026-11-14';backup.mkdir(exist_ok=True)
    for name in ('build.json','active.json'):
        if not (backup/name).exists():shutil.copy2(RES/name,backup/name)
    for rel in ('f/a/fab72152d7112058','e/5/e50ef81ba77ae51a','AppRes.info'):
        dest=backup/'baseline'/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():shutil.copy2(RES/'baseline'/rel,dest)
        target=RES/'baseline'/rel;shutil.copy2(game/rel,target)
    old['initial_installed']=report['tracked_originals'];old['base_profile']='Verified pristine build; no imported substitutions'
    for rel,h in old['initial_installed'].items():
        if sha_file(game/rel)!=h:raise ValueError('Game changed during app resource reset: '+rel)
    save_json(RES/'build.json',old);save_json(RES/'active.json',[]);save_json(RES/'base-effects.json',{'weapon':[],'skill':[]})
    save_json(ROOT/'reports/pristine-app-resource-base.json',{'prepared':True,'original_hashes':old['initial_installed'],'previous_base_preserved':str(backup),'game_files_modified':False})
    print('Application resources now bound to clean originals, with no inherited mod selections.')
if __name__=='__main__':main()
