"""Special-route candidate integration checks. Does not install files."""
import json
from pathlib import Path
from full_engine import FullEngine
from core import save_json,sha_file
ROOT=Path('D:/naraka_unlocker')
def main():
    e=FullEngine(ROOT/'work/atelier-pristine-qa');before={p:sha_file(e.game/p) for p in e.manifest['initial_installed']}
    seq=json.loads((ROOT/'reports/full-engine-special-selections.json').read_text())
    p,h=e.build(seq,lambda m:print(m,flush=True))
    assert all(sha_file(e.game/p)==v for p,v in before.items())
    save_json(ROOT/'reports/full-engine-special-validation.json',{'passed':True,'candidate':str(p),'hashes':h,'selections':seq,'game_files_modified':False})
    print('SPECIAL_BATCH_PASSED',flush=True)
if __name__=='__main__':main()
