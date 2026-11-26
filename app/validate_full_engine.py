"""Candidate-only integration checks; never installs resources."""
import json
from pathlib import Path
from full_engine import FullEngine
from core import save_json,sha_file

ROOT=Path('D:/naraka_unlocker')
def main():
    e=FullEngine(ROOT/'work/atelier-pristine-qa')
    before={p:sha_file(e.game/p) for p in e.manifest['initial_installed']}
    s=json.loads((ROOT/'reports/full-engine-batch-selections.json').read_text())
    p,h=e.build(s,lambda m:print(m,flush=True))
    assert all(sha_file(e.game/p)==v for p,v in before.items())
    save_json(ROOT/'reports/full-engine-batch-validation.json',{'passed':True,'candidate':str(p),'hashes':h,'selections':s,'game_files_modified':False})
    print('BATCH_PASSED',flush=True)
if __name__=='__main__':main()
