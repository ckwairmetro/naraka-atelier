"""Mock installation checks for the catalogue-wide compiler. No real writes."""
import copy,json,shutil,tempfile,threading,unittest,os
from pathlib import Path
from unittest.mock import patch
import generalized
from full_engine import FullEngine
from core import Trial,sha_file,save_json,COMMON

class FullEngineChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='atelier-full-tests-');cls.root=Path(cls.temp.name)
        cls.real=FullEngine(cls.root/'read-only');cls.before={p:sha_file(cls.real.game/p) for p in cls.real.manifest['initial_installed']}
    @classmethod
    def tearDownClass(cls):
        assert all(sha_file(cls.real.game/p)==h for p,h in cls.before.items()),'Real game changed'
        cls.temp.cleanup()
    def test_catalogue_and_defaults_available(self):
        self.assertEqual(sum(not i.get('synthetic') for i in self.real.items.values()),6507)
        self.assertFalse([i['key'] for i in self.real.items.values() if not i['support']['available']])
    def test_effect_requires_correct_model(self):
        fx={'source':'weapon:2311500','target':'effect:w10043','hero':None}
        with self.assertRaisesRegex(ValueError,'requires its native weapon'):self.real.validate([fx])
        self.real.validate([{'source':'weapon:2311500','target':'weapon:2311558','hero':None},fx])
    def test_unknown_and_bad_number_options_rejected(self):
        s={'source':'hair:100036','target':'hair:100097','hero':1000004}
        for options in ({'private_path':'x'},{'sliders':[-1,38,100]},{'colors':[0,0,9999]}):
            with self.assertRaises(ValueError):self.real.validate([dict(s,options=options)])
    def test_empty_accessory_source(self):
        s={'source':'accessory:empty:1000004:1003','target':'accessory:3410229','hero':1000004}
        self.real.validate([s]);self.assertEqual(self.real.recipes(s),[])
    def test_showcase_hero_restriction(self):
        source=next(i for i in self.real.items.values() if i['c']=='pose' and i.get('h')==[1000004])
        target=next(i for i in self.real.items.values() if i['c']=='pose' and i.get('h') and 1000004 not in i['h'])
        with self.assertRaisesRegex(ValueError,'showcase item'):self.real.validate([{'source':source['key'],'target':target['key'],'hero':1000004}])
    def test_shared_outfit_lookup_rejected(self):
        s=[{'source':'outfit:3400100','target':'outfit:3400117','hero':1000004},
           {'source':'outfit:3400101','target':'outfit:3400118','hero':1000004}]
        with self.assertRaisesRegex(ValueError,'share a native'):self.real.validate(s)
    def test_apply_and_restore_complete_outfit_in_mock(self):
        e=copy.copy(self.real);e.state=self.root/'operation';e.state.mkdir();e.game=e.state/'mock-game';e.game.mkdir();e.mutex=threading.Lock();e.pending=None
        files=[COMMON,'7/d/7d94d92897d908a5','e/5/e50ef81ba77ae51a','AppRes.info'];expected={}
        # A user's live game can already be modded. Use verified pristine inputs
        # for this mock fixture, not live bytes paired with a pristine index.
        source_file=Path(os.environ.get('LOCALAPPDATA',''))/'Naraka Atelier/source-manifest.json'
        sources=json.loads(source_file.read_text(encoding='utf8')) if source_file.exists() else {}
        for rel in files:
            source=e.resources/'baseline'/rel
            if not source.exists():source=Path(sources[rel]['path']) if rel in sources else self.real.game/rel
            self.assertEqual(sha_file(source),e.manifest['initial_installed'][rel])
            dst=e.game/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dst);expected[rel]=sha_file(dst)
        e.manifest=dict(e.manifest,critical={});e.disk={'selections':[],'expected':expected,'generation':None}
        pair={'source':'outfit:3400100','target':'outfit:3400117','hero':1000004}
        with patch('generalized.ensure_closed',lambda:None),patch('generalized.Trial',lambda *a,**kw:Trial(*a,**kw,check_closed=lambda:None)):
            e.apply([pair]);self.assertEqual(e.disk['selections'],[pair]);self.assertTrue(e.check_build(strict=True)['ok'])
            e.apply([]);self.assertEqual(e.disk['expected'],expected)
        self.assertTrue(all(sha_file(e.game/p)==h for p,h in expected.items()));self.assertIsNone(e.pending)

if __name__=='__main__':unittest.main(verbosity=2)
