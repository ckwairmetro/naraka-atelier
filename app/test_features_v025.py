"""Profile feature validation and transactional feature persistence on fake files."""
import json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from collections import namedtuple
from full_engine import FullEngine
from generalized import GeneralizedEngine
from core import Trial,sha_file,save_json

class FeatureChecks(unittest.TestCase):
    def test_legacy_reveal_is_migrated_and_bad_values_rejected(self):
        e=FullEngine.__new__(FullEngine);e.disk={'experiment':{'name':'Global cosmetic menu reveal'}}
        self.assertEqual(e.resolve_features(),{'global_reveal':True})
        e.disk={'features':{'global_reveal':False},'experiment':{'name':'Global cosmetic menu reveal'}}
        self.assertEqual(e.resolve_features(),{'global_reveal':False})
        for bad in ({'other':True},{'global_reveal':1},{'global_reveal':'yes'},[],True):
            with self.assertRaises(ValueError):e.resolve_features(bad)
    def fake(self,root,report_features):
        game=root/'game';candidate=root/'candidate';game.mkdir();candidate.mkdir();before={};after={}
        for name,old,new in [('common','original','revealed'),('AppRes.info','old-index','new-index')]:
            (game/name).write_text(old);(candidate/name).write_text(new);before[name]=sha_file(game/name);after[name]=sha_file(candidate/name)
        save_json(candidate/'validation.json',{'features':report_features,'before':before,'base_files':{},'bundles':{}})
        e=GeneralizedEngine.__new__(GeneralizedEngine);e.state=root;e.game=game;e.disk={'features':{'global_reveal':False},'expected':before,'selections':[]};e.pending=None;e.mutex=threading.Lock();e.validate=lambda s:[];e.check_build=lambda strict=False:{'ok':True};e.resolve_features=lambda f=None:{'global_reveal':False} if f is None else f
        def build(ss,progress):
            self.assertEqual(e._active_features,{'global_reveal':True});return candidate,after
        e.build=build;return e,before
    def test_feature_is_committed_with_profile_and_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            e,_=self.fake(Path(tmp),{'global_reveal':True});disk=namedtuple('Disk','total used free')(100_000_000_000,0,100_000_000_000);seen=[]
            def trial(*args):
                journal=json.loads((e.state/'pending.json').read_text());seen.append(journal);return Trial(*args,check_closed=lambda:None)
            with patch('generalized.ensure_closed',lambda:None),patch('generalized.shutil.disk_usage',return_value=disk),patch('generalized.Trial',trial):e.apply([],features={'global_reveal':True})
            self.assertTrue(e.disk['features']['global_reveal']);self.assertTrue(seen[0]['new_features']['global_reveal']);self.assertFalse(seen[0]['old_profile']['features']['global_reveal']);self.assertNotIn('_active_features',e.__dict__)
    def test_mismatched_candidate_feature_never_writes_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            e,before=self.fake(Path(tmp),{'global_reveal':False});disk=namedtuple('Disk','total used free')(100_000_000_000,0,100_000_000_000)
            with patch('generalized.ensure_closed',lambda:None),patch('generalized.shutil.disk_usage',return_value=disk):
                with self.assertRaisesRegex(ValueError,'requested appearance features'):e.apply([],features={'global_reveal':True})
            self.assertFalse((e.state/'pending.json').exists());self.assertEqual({p:sha_file(e.game/p) for p in before},before)

if __name__=='__main__':unittest.main(verbosity=2)
