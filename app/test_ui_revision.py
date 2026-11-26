"""Mode/slot/status regressions and accepted native fixtures. No game writes."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from full_engine import FullEngine
from main import status_payload
from hair_studio import capabilities,validate,uniform,dye_tree
from advanced_recipes import color_tree
from bundle_editor import BundleEditor

ROOT=Path('D:/naraka_unlocker')

class RevisionChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='atelier-v021-');cls.engine=FullEngine(cls.tmp.name)
        cls.palette=json.loads((cls.engine.resources/'palette.json').read_text())
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def hair(self,id,opts):
        return self.engine.validate([{'source':'hair:100036','target':'hair:'+str(id),'hero':1000004,'options':opts}])
    def test_no_silent_dye_discard(self):
        with self.assertRaisesRegex(ValueError,'Choose a dye mode'):self.hair(100076,{'colors':[36]})
    def test_exclusive_controls(self):
        self.hair(100076,{'color_mode':'plain','hsv':[25,70,50]})
        self.hair(100076,{'color_mode':'flourish','colors':[36]})
        self.hair(100097,{'color_mode':'gradient','colors':[12,10,18],'sliders':[35,38,100]})
        for mode,data in [('plain',{'hsv':[20,20,20],'colors':[36]}),('flourish',{'colors':[36],'sliders':[35,38,100]}),('gradient',{'colors':[12,10,18],'sliders':[35,38,100],'regions':[0]})]:
            with self.assertRaises(ValueError):self.hair(100076,dict(data,color_mode=mode))
    def test_legacy_uniform_still_accepted(self):
        self.hair(100097,{'color_mode':'solid','colors':[36,36,36],'sliders':[35,38,100],'regions':list(range(8))})
    def test_highlights_are_hairstyle_specific(self):
        e=self.engine
        self.assertFalse(capabilities(e,e.items['hair:100076'])['highlights'])
        self.assertFalse(capabilities(e,e.items['hair:100097'])['highlights'])
        for id in [100076,100097]:
            with self.assertRaises(ValueError):self.hair(id,{'color_mode':'streaks','parts':[{'group':140,'mode':'flourish','colors':[36]}]})
        cap=capabilities(e,e.items['hair:100038']);self.assertTrue(cap['highlights'])
        g=next(g for g in cap['groups'] if not g['base'])
        self.hair(100038,{'color_mode':'streaks','parts':[{'group':g['id'],'mode':'flourish','colors':[36],'intensity':50}]})
        with self.assertRaises(ValueError):self.hair(100038,{'color_mode':'streaks','parts':[{'group':140,'mode':'flourish','colors':[36]}]})
    def test_outfit_effect_has_one_receiver_slot(self):
        effects=[i for i in self.engine.items.values() if i['c']=='effect' and i['kind']=='outfit']
        a=effects[0];b=next(i for i in effects if i['type']!=a['type'])
        with self.assertRaisesRegex(ValueError,'same receiver slot'):
            self.engine.validate([{'source':'outfit:3400100','target':i['key'],'hero':1000004} for i in (a,b)])
    def test_current_profile_still_valid(self):
        import os
        p=Path(os.environ['LOCALAPPDATA'])/'Naraka Atelier/profile.json'
        self.engine.validate(json.loads(p.read_text(encoding='utf8'))['selections'])
    def test_plain_colour_keeps_target_lighting(self):
        tree=json.loads((ROOT/'reports/yuer-hair-custom-data.json').read_text(encoding='utf8'))['tree']
        out=uniform(tree,hsv=[0,100,100])
        for old,new in zip(tree['serializedCustomHairData'],out['serializedCustomHairData']):
            self.assertAlmostEqual(new['BaseColorA']['r'],.82,places=6)
            self.assertEqual(new['BaseColorA']['g'],0)
            for k in ('BaseKs','BaseKsBoost','BaseGlossMapScale'):self.assertEqual(old[k],new[k])
    def test_partial_highlights_preserve_unselected_regions(self):
        tree=json.loads((ROOT/'reports/yuer-hair-custom-data.json').read_text(encoding='utf8'))['tree']
        opts={'color_mode':'streaks','parts':[{'group':140,'mode':'flourish','colors':[36],'intensity':50}]}
        with patch('hair_studio.capabilities',return_value={'groups':[{'id':140,'parts':[2,5,7]}]}):
            out=dye_tree(self.engine,self.engine.items['hair:100097'],tree,self.palette,opts)
        for old,new in zip(tree['serializedCustomHairData'],out['serializedCustomHairData']):
            self.assertEqual(old['BaseColorA'],new['BaseColorA'])
            for n,(a,b) in enumerate(zip(old['unpackedPartData'],new['unpackedPartData']),1):
                if n in (2,5,7):self.assertEqual(b['HighLightingAmount'],.5)
                else:self.assertEqual(dict(a,HairIDs=0),b)
    def test_skill_metadata_uses_native_group_identity(self):
        a,b=self.engine.items['skill:104001'],self.engine.items['skill:104002']
        self.assertEqual(a['_effectGroups'],b['_effectGroups'])
        self.assertEqual(len(a['_affectedSkills']),3)
        self.assertFalse(set(a['_affectedSkills'])&set(self.engine.items['skill:104004']['_affectedSkills']))
        self.engine.validate([{'source':'outfit:3400100','target':'skill:'+str(id),'hero':1000004} for id in (104001,104004)])
    def test_busy_status_does_not_report_interruption(self):
        e=copy.copy(self.engine);e.job={'busy':True,'message':'Applying','error':None};e.pending={'candidate':'test'}
        with patch.object(e,'check_build',side_effect=AssertionError('should not compare old profile during writes')):
            r=status_payload(e);self.assertFalse(r['build']['ok']);self.assertEqual(r['build']['state'],'applying');self.assertEqual(r['build']['errors'],[])
    def test_idle_recovery_guard_remains(self):
        e=copy.copy(self.engine);e.job={'busy':False};e.pending={'candidate':'test'}
        with patch.object(e,'check_build',return_value={'ok':False,'errors':['An interrupted operation needs recovery']}):
            r=status_payload(e);self.assertTrue(r['pending']);self.assertFalse(r['build']['ok'])
    def test_accepted_uniform_and_gradient_fixtures(self):
        live=BundleEditor(self.engine.game/'b/7/b76f2d0f2be1fbc2',ROOT/'work/ui-hair-investigation/cache')
        opened=[live]
        try:
            for kind,opts in [('kujin',{'color_mode':'flourish','colors':[36]}),('gradient',{'color_mode':'gradient','colors':[12,10,18],'sliders':[35,38,100]})]:
                accepted=BundleEditor(ROOT/f'work/matari-yuer-{kind}-candidate/StreamingAssets/b/7/b76f2d0f2be1fbc2',ROOT/'work/ui-hair-investigation/cache');opened.append(accepted)
                for suffix in ('','_ui'):
                    p=f'assets/res/character/hair_custom_data/ch_f_hanhaimomin_hair_lv_s6{suffix}/hair_custom_data_01.asset'
                    c,en=live.asset(p);tree=c.tree(en['asset']['m_PathID']);dst,den=accepted.asset(p)
                    result=dye_tree(self.engine,self.engine.items['hair:100097'],tree,self.palette,opts)
                    self.assertEqual(result,dst.tree(den['asset']['m_PathID']))
                    self.assertEqual(dst.sf.objects[den['asset']['m_PathID']].save_typetree(result),dst.sf.objects[den['asset']['m_PathID']].get_raw_data())
        finally:
            for b in opened:b.close()

if __name__=='__main__':unittest.main(verbosity=2)
