"""Exercise the real HTTP job protocol with a fake writer; no game access."""
import argparse,json,re,tempfile,threading,time,unittest,urllib.request
from pathlib import Path
from unittest.mock import patch
import main

class FakeEngine:
    def __init__(self,state):
        self.state=Path(state);self.manifest={'critical':{},'catalogue_version':'test'}
        self.disk={'expected':{},'selections':[]};self.pending=None
        self.job={'busy':False,'percent':0,'message':'Idle','error':None}
        self.release=threading.Event();self.count=0
    def validate(self,selections):return []
    def resolve_features(self,features=None):return {}
    def check_build(self):return {'ok':True,'version':'test','errors':[]}
    def apply(self,selections,progress,features=None):
        self.count+=1;progress('Compiling 1/72 · outfit 3400153')
        if not self.release.wait(15):raise RuntimeError('Test did not release fake writer')
        return {'files':4 if self.count==1 else 1,'unchanged_files':3,'reused_bundles':3}

class JobProtocol(unittest.TestCase):
    def test_each_apply_ack_and_status_belong_to_new_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp);created=[]
            def factory(s):
                engine=FakeEngine(s);created.append(engine);return engine
            args=argparse.Namespace(state_dir=tmp,compile_only=None,no_browser=True,browser=False,port=0)
            with patch.object(main,'Engine',factory):
                server=threading.Thread(target=main.run_app,args=(args,),daemon=True);server.start()
                deadline=time.monotonic()+10
                while not (state/'session.json').exists():
                    self.assertLess(time.monotonic(),deadline);time.sleep(.02)
                url=json.loads((state/'session.json').read_text())['url'];html=urllib.request.urlopen(url).read().decode()
                token=re.search(r"SESSION_TOKEN\s*=\s*'([^']+)'",html).group(1)
                def api(path,payload=None):
                    req=urllib.request.Request(url+'/api/'+path,headers={'X-Session-Token':token,'Content-Type':'application/json'},data=None if payload is None else json.dumps(payload).encode())
                    return json.load(urllib.request.urlopen(req,timeout=10))
                def finished():
                    deadline=time.monotonic()+10
                    while True:
                        status=api('status')
                        if not status['job']['busy']:return status
                        self.assertLess(time.monotonic(),deadline);time.sleep(.02)
                try:
                    one=api('apply',{'selections':[]})['job'];self.assertEqual(one['percent'],2);self.assertTrue(one['busy']);self.assertNotIn('result',one)
                    created[0].release.set();complete=finished()['job'];self.assertEqual(complete['percent'],100);self.assertEqual(complete['result']['files'],4)
                    created[0].release.clear();two=api('apply',{'selections':[]})['job']
                    self.assertNotEqual(one['id'],two['id']);self.assertEqual(two['percent'],2);self.assertTrue(two['busy']);self.assertNotIn('result',two)
                    busy=api('status')['job'];self.assertEqual(busy['id'],two['id']);self.assertTrue(busy['busy']);self.assertLess(busy['percent'],100);self.assertNotIn('result',busy)
                    created[0].release.set();complete=finished()['job'];self.assertEqual(complete['id'],two['id']);self.assertEqual(complete['result']['files'],1)
                finally:
                    created[0].release.set();finished();api('shutdown',{});server.join(5)
                self.assertFalse(server.is_alive())

if __name__=='__main__':unittest.main(verbosity=2)
