"""Tests only write a disposable mock installation, never the real game."""
import copy,json,tempfile,threading,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import core
from core import Engine,COMMON,import_catalogue,sha_file,load_sf,unpack_logical,load_table,section_rows

class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.real=Engine(cls.root/'readonly-engine')
        cls.before={p:sha_file(cls.real.game/p) for p in cls.real.manifest['initial_installed']}
        cls.counter=0
    @classmethod
    def tearDownClass(cls):
        for p,h in cls.before.items():assert sha_file(cls.real.game/p)==h,'Real game changed during mock test'
        cls.temp.cleanup()
    def setUp(self):
        type(self).counter+=1;e=copy.copy(self.real);e.state=self.root/('state'+str(self.counter));e.state.mkdir()
        e.game=e.state/'mock-game';e.game.mkdir();e.mutex=threading.Lock();e.pending=None
        expected={p:sha_file(e.resources/'baseline'/p) for p in (COMMON,'AppRes.info')}  # pristine baseline written below; the real game may carry applied swaps
        for p in expected:
            target=e.game/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((e.resources/'baseline'/p).read_bytes())
        e.manifest=dict(e.manifest,critical={},initial_installed=expected)
        e.disk={'selections':[],'expected':expected,'generation':None};self.e=e
        self.pair={'source':'weapon:2310000','target':'weapon:2310012','hero':None}
    def test_full_catalogue_audited(self):
        self.assertEqual(len(self.e.items),6507)
        self.assertEqual(sum(v['total'] for v in self.e.coverage.values()),6507)
        self.assertTrue(all('support' in i for i in self.e.items.values()))
    def test_cross_family_and_hero_rejected(self):
        with self.assertRaises(ValueError):self.e.validate([dict(self.pair,target='weapon:2312301')])
        with self.assertRaises(ValueError):self.e.validate([{'source':'hair:100036','target':'hair:100097','hero':1000001}])
    def test_source_duplicate_and_cycle_rejected(self):
        with self.assertRaises(ValueError):self.e.validate([self.pair,self.pair])
        with self.assertRaises(ValueError):self.e.validate([self.pair,dict(self.pair,source='weapon:2310012',target='weapon:2310000')])
    def test_specialized_outfit_blocked(self):
        with self.assertRaises(ValueError):self.e.validate([{'source':'outfit:3400100','target':'outfit:3400145','hero':1000004}])
    def test_compile_native_and_preserve_identity(self):
        selections=[self.pair,{'source':'hair:100036','target':'hair:100040','hero':1000004}]
        layout,hashes=self.e.build(selections);self.assertEqual(set(hashes),{COMMON,'AppRes.info'})
        a,_=unpack_logical(self.e.resources/'baseline'/COMMON);b,_=unpack_logical(layout/COMMON);sa,sb=load_sf(a),load_sf(b)
        _,_,old=load_table(sa,self.e.pids['WeaponSkin'],'WeaponSkin');_,_,new=load_table(sb,self.e.pids['WeaponSkin'],'WeaponSkin')
        _,_,om=section_rows(old,'WeaponSkin_WeaponSkin');_,_,nm=section_rows(new,'WeaponSkin_WeaponSkin')
        before=self.e.decoder.row('WeaponSkin_WeaponSkin',om[2310000]);after=self.e.decoder.row('WeaponSkin_WeaponSkin',nm[2310000])
        for k in ('_ID','_SkinName','_ShopUnlock','_WeaponTypePresentation'):self.assertEqual(before[k],after[k])
        self.assertEqual(after['_Quality'],self.e.row('WeaponSkin','WeaponSkin_WeaponSkin',2310012)['_Quality'])
    def test_compile_every_enabled_adapter_together(self):
        active=self.e.baseline_active();selections=[]
        for category in ('weapon','hair','accessory','grapple','background','pose','platform','broadcast','lootpile','rescue'):
            candidates=[i for i in self.e.items.values() if i['c']==category and i['support']['available'] and (not i.get('h') or 1000004 in i['h'])]
            preferred=next((self.e.items[s['source']] for s in active if s['source'].startswith(category+':') and s['source'] in self.e.items and self.e.items[s['source']]['support']['available']),candidates[0])
            target=next(i for i in candidates if not self.e.compatible(preferred,i,1000004))
            selections.append({'source':preferred['key'],'target':target['key'],'hero':1000004})
        layout,_=self.e.build(selections)
        report=json.loads((layout/'validation.json').read_text());self.assertTrue(report['passed']);self.assertEqual(len(report['selections']),10)
    def test_apply_and_restore_prior_profile(self):
        real=core.Trial
        with patch('core.ensure_closed',lambda:None),patch('core.Trial',lambda *a,**k:real(*a,**k,check_closed=lambda:None)):
            self.e.apply([self.pair]);self.assertEqual(len(self.e.disk['selections']),1)
            self.e.apply([]);self.assertEqual(self.e.disk['expected'],self.e.manifest['initial_installed'])
            self.assertIsNone(self.e.pending)
    def test_partial_write_failure_recovery(self):
        real=core.Trial
        class Failing(real):
            failed=False
            def replace(self,source,relative,old,new):
                if relative=='AppRes.info' and not self.failed:
                    self.failed=True;raise OSError('Simulated index failure')
                return super().replace(source,relative,old,new)
        with patch('core.ensure_closed',lambda:None),patch('core.Trial',lambda *a,**k:Failing(*a,**k,check_closed=lambda:None)):
            with self.assertRaises(OSError):self.e.apply([self.pair])
        for p,h in self.e.manifest['initial_installed'].items():self.assertEqual(sha_file(self.e.game/p),h)
        with patch('core.ensure_closed',lambda:None),patch('core.Trial',lambda *a,**k:real(*a,**k,check_closed=lambda:None)):self.e.recover()
        self.assertIsNone(self.e.pending)
    def test_unknown_resource_refused(self):
        (self.e.game/'AppRes.info').write_bytes(b'unknown update')
        self.assertFalse(self.e.check_build(strict=True)['ok'])
        with patch('core.ensure_closed',lambda:None):
            with self.assertRaises(ValueError):self.e.apply([self.pair])
        self.assertEqual((self.e.game/'AppRes.info').read_bytes(),b'unknown update')
    def test_running_game_refused_before_writes(self):
        with patch('core.ensure_closed',side_effect=RuntimeError('Game running')):
            with self.assertRaises(RuntimeError):self.e.apply([self.pair])
        self.assertFalse((self.e.state/'pending.json').exists())
    def test_zip_traversal_and_old_version_rejected(self):
        p=self.e.state/'bad.zip'
        with zipfile.ZipFile(p,'w') as z:z.writestr('../escape','no')
        with self.assertRaises(ValueError):import_catalogue(p,self.e.state/'imports','1.5.9.2')
        with zipfile.ZipFile(p,'w') as z:z.writestr('naraka-catalogue/data.js','window.CATALOG = '+json.dumps({'gameVersion':{'clientVersion':'0.0'},'items':[],'heroes':[1]})+';')
        with self.assertRaises(ValueError):import_catalogue(p,self.e.state/'imports','1.5.9.2')

if __name__=='__main__':unittest.main(verbosity=2)
