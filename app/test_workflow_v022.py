"""Native policy, numeric preflight and real transactional delta writes on a mock game."""
import copy,json,tempfile,threading,unittest,hashlib,os
from pathlib import Path
from unittest.mock import patch
from collections import namedtuple
from full_engine import FullEngine
from generalized import GeneralizedEngine
from core import Trial,save_json,sha_file
from bundle_editor import BundleEditor,proof_digest

class WorkflowChecks(unittest.TestCase):
    def test_cache_proof_numeric_ids_roundtrip(self):
        p={'opaque':{20:8,3:9,-10:12,-2:10}};self.assertEqual(proof_digest(p),proof_digest(json.loads(json.dumps(p))))
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='atelier-v022-');cls.root=Path(cls.temp.name);cls.e=FullEngine(cls.root/'engine')
        # Native copy builds use the already preserved pristine source snapshots,
        # never adopt the user's currently substituted installed bundles.
        sources=Path(os.environ['LOCALAPPDATA'])/'Naraka Atelier/source-manifest.json'
        if sources.exists():save_json(cls.e.state/'source-manifest.json',json.loads(sources.read_text()))
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_universe_slash_only_dual_blades(self):
        item=self.e.items['effect:w10005'];self.assertEqual(item['_weaponFamilies'],[self.e.items['weapon:2311558']['w']])
        self.assertIsNotNone(self.e.compatible(self.e.items['weapon:2311837'],item))
    def test_copy_flag_is_not_a_runtime_dependency(self):
        self.assertTrue(self.e.effect_fits_weapon(2314008,10046))
        self.e.validate([{'source':'weapon:2314016','target':'weapon:2314008','hero':None},{'source':'weapon:2314016','target':'effect:w10046','hero':None}])
    def test_dragon_exclusive_requires_real_controller(self):
        self.assertFalse(self.e.effect_fits_weapon(2311547,10043));self.assertTrue(self.e.effect_fits_weapon(2311558,10043))
        self.e.validate([{'source':'weapon:2311522','target':'weapon:2311558','hero':None},{'source':'weapon:2311522','target':'effect:w10043','hero':None}])
    def test_native_weapon_can_be_effect_receiver_without_model_change(self):
        self.e.validate([{'source':'weapon:2311558','target':'weapon:2311558','hero':None},{'source':'weapon:2311558','target':'effect:w10043','hero':None}])
    def test_quality_is_cosmetic_skin_quality(self):
        jobs=self.e.recipes({'source':'weapon:2310032','target':'weapon:2310049','hero':None})
        self.assertIn('_Quality',jobs[0][-1]);self.assertNotIn('_WeaponItemType',jobs[1][-1])
    def test_number_range_is_visible_and_validated_before_apply(self):
        c=next(c for c in self.e.controls('weapon:2310049') if c['key']=='numbers');self.assertEqual([(f['min'],f['max']) for f in c['fields']],[(0,999),(0,999),(0,999),(0,1)])
        bad=[{'source':'weapon:2310032','target':'weapon:2310049','hero':None,'options':{'numbers':[1000,999,999,1]}}]
        with patch('generalized.ensure_closed',side_effect=AssertionError('should fail first')):
            with self.assertRaises(ValueError):self.e.apply(bad)
    def test_native_band_failure_precedes_any_file_write(self):
        s=[{'source':'weapon:2310032','target':'weapon:2310049','hero':None,'options':{'numbers':[987,986,985,1]}}]
        self.e.numbered_plans={}
        with patch('advanced_recipes.pin_rule_config',side_effect=ValueError('outside native rule bands')),patch('generalized.ensure_closed',side_effect=AssertionError('must not touch files')):
            with self.assertRaisesRegex(ValueError,'native rule bands'):self.e.apply(s)
    def test_current_sixty_selections_remain_valid(self):
        p=Path('D:/naraka_unlocker/work/before-v022-profile.json');ss=json.loads(p.read_text(encoding='utf8'))['selections'];self.e.numbered_plans={};self.e.validate(ss);self.assertEqual(len(ss),60)
    def test_delta_apply_writes_only_changed_files(self):
        state=self.root/'delta';game=state/'mock-game';candidate=state/'candidate';game.mkdir(parents=True);candidate.mkdir()
        originals={};hashes={}
        for name,old,new in [('unchanged','retained','retained'),('changed','before','after'),('AppRes.info','old-index','new-index')]:
            (game/name).write_text(old);(candidate/name).write_text(new);originals[name]=sha_file(game/name);hashes[name]=sha_file(candidate/name)
        save_json(candidate/'validation.json',{'before':originals,'base_files':{},'bundles':{}})
        engine=GeneralizedEngine.__new__(GeneralizedEngine);engine.state=state;engine.game=game;engine.mutex=threading.Lock();engine.disk={'expected':originals,'selections':[]};engine.pending=None;engine.validate=lambda s:[];engine.check_build=lambda strict=False:{'ok':True};engine.build=lambda s,p:(candidate,hashes)
        before=(game/'unchanged').stat().st_mtime_ns;messages=[];Disk=namedtuple('Disk','total used free')
        with patch('generalized.ensure_closed',lambda:None),patch('generalized.shutil.disk_usage',return_value=Disk(100_000_000_000,0,100_000_000_000)),patch('generalized.Trial',lambda *a:Trial(*a,check_closed=lambda:None)):
            result=engine.apply([],messages.append)
        self.assertEqual(result['written_files'],['changed','AppRes.info']);self.assertEqual(result['files'],2);self.assertEqual(result['unchanged_files'],1)
        self.assertEqual((game/'unchanged').stat().st_mtime_ns,before);self.assertEqual((game/'changed').read_text(),'after');self.assertFalse((state/'pending.json').exists())
        self.assertTrue(any(isinstance(m,dict) and m.get('phase')=='write' for m in messages))
    def test_packed_bundle_cache_reuses_only_exact_verified_payload(self):
        e=self.e;b=BundleEditor(e.resources/'baseline/f/a/fab72152d7112058',self.root/'cache')
        try:
            c=b.cab();pid=c.abobj.path_id;t=c.tree(pid);t['m_Name']+='-cache-test';c.put(pid,t)
            a=b.pack(self.root/'first',self.root/'packing-first');second=b.pack(self.root/'second',self.root/'packing-second')
            self.assertFalse(a['reused_verified_candidate']);self.assertTrue(second['reused_verified_candidate']);self.assertEqual(sha_file(self.root/'first'),sha_file(self.root/'second'))
            record=next((self.root/'cache/packed').glob('*/proof.json'));original=record.read_bytes();data=json.loads(original);data['crc']+=1;record.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'cache metadata'):b.pack(self.root/'bad-metadata',self.root/'packing-bad-metadata')
            record.write_bytes(original)
            artifact=next((self.root/'cache/packed').glob('*/bundle'));artifact.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'cache identity'):b.pack(self.root/'third',self.root/'packing-third')
        finally:b.close()
    def test_staged_common_pack_cache_preserves_baseline(self):
        baseline=self.e.resources/'baseline/f/a/fab72152d7112058';before=sha_file(baseline)
        choices=[{'source':'weapon:2313000','target':'weapon:2313012','hero':None}]
        first,a=self.e.build(choices);second,b=self.e.build(choices)
        self.assertEqual(a,b);self.assertEqual(sha_file(baseline),before)
        self.assertTrue(json.loads((second/'validation.json').read_text())['bundles']['f/a/fab72152d7112058']['reused_verified_candidate'])
    def test_standalone_colours_are_automatic_and_legacy_settings_remain_valid(self):
        self.assertNotIn('preview_colours',{c['key'] for c in self.e.controls('weapon:2310049')})
        s={'source':'weapon:2310032','target':'weapon:2310049','hero':None}
        for value in (0,1):
            self.e.validate([dict(s,options={'preview_colours':value})])
        for value in (True,2,'1'):
            with self.assertRaises(ValueError):self.e.validate([dict(s,options={'preview_colours':value})])
        with self.assertRaisesRegex(ValueError,'Unsupported options'):
            self.e.validate([{'source':'weapon:2313000','target':'weapon:2313012','hero':None,'options':{'preview_colours':1}}])
    def test_default_and_legacy_off_compile_the_confirmed_colour_path(self):
        selection={'source':'weapon:2310032','target':'weapon:2310049','hero':None,'options':{'numbers':[999,999,999,1]}}
        first,a=self.e.build([selection]);proof=json.loads((first/'validation.json').read_text())
        aliases=[p for p in proof['advanced'] if p['type']=='standalone_preview_colour_initialization']
        self.assertEqual(len(aliases),1);self.assertEqual(aliases[0]['source'],2310032);self.assertEqual(aliases[0]['target'],2310049)
        self.assertTrue(aliases[0]['paid_operations_disabled']);self.assertFalse(aliases[0]['account_state_changed'])
        selection['options']['preview_colours']=0
        second,b=self.e.build([selection]);self.assertEqual(a,b)

if __name__=='__main__':unittest.main(verbosity=2)
