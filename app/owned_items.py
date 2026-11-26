"""User-declared ownership preferences; never reads or writes game state."""
import json,re
from core import save_json

def load(engine):
    path=engine.state/'owned-items.json'
    if not path.exists():return {'keys':[],'scopes':[]}
    data=json.loads(path.read_text(encoding='utf8'))
    return {'keys':[k for k in data.get('keys',[]) if k in engine.items],
            'scopes':data.get('scopes',[])}

def save(engine,data):
    if not isinstance(data,dict) or set(data)!={'keys','scopes'}:raise ValueError('Expected ownership keys and scopes')
    keys,scopes=data['keys'],data['scopes']
    if not isinstance(keys,list) or len(keys)>20000 or any(not isinstance(k,str) or k not in engine.items for k in keys):raise ValueError('Unknown ownership item')
    if not isinstance(scopes,list) or len(scopes)>2000 or any(not isinstance(s,str) or not re.fullmatch(r'[a-z]+:\d+:\d+',s) for s in scopes):raise ValueError('Invalid ownership scope')
    value={'keys':sorted(set(keys)),'scopes':sorted(set(scopes))}
    save_json(engine.state/'owned-items.json',value)
    return value
