"""Final fault-injection checks; all writes stay in temporary mock games."""
import json,tempfile,unittest,threading
from pathlib import Path
from unittest.mock import patch
from core import Trial,sha_file,save_json,Engine

class PowerLoss(BaseException):pass

class FinalTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='atelier-final-fault-');self.root=Path(self.temp.name);game=self.root/'game';candidate=self.root/'candidate';game.mkdir();candidate.mkdir();old={};new={}
        for name in ['first','second','AppRes.info']:
            (game/name).write_bytes(('old-'+name).encode());(candidate/name).write_bytes(('new-'+name).encode());old[name]=sha_file(game/name);new[name]=sha_file(candidate/name)
        self.t=Trial(game,candidate,self.root/'transaction',old,new,check_closed=lambda:None)
    def tearDown(self):self.temp.cleanup()
    def test_index_always_installed_last_and_restored_first(self):
        calls=[];original=self.t.replace
        def replace(source,name,*rest):calls.append(name);return original(source,name,*rest)
        self.t.replace=replace;self.t.apply();self.assertEqual(calls,['first','second','AppRes.info']);calls.clear();self.t.restore();self.assertEqual(calls,['AppRes.info','second','first'])
    def test_crash_after_rename_before_journal_update_recovers(self):
        original=self.t.replace
        def crash(*args):original(*args);raise PowerLoss()
        self.t.replace=crash
        with self.assertRaises(PowerLoss):self.t.apply()
        self.assertEqual(json.loads(self.t.state_file.read_text())['written'],[])
        self.t.replace=original;self.t.restore();self.assertEqual(self.t.status()['installed'],self.t.originals)
    def test_failed_index_install_rolls_back_all_bundles(self):
        original=self.t.replace
        def fail(source,name,*rest):
            if name=='AppRes.info' and source.is_relative_to(self.t.candidate):raise OSError('index install failed')
            return original(source,name,*rest)
        self.t.replace=fail
        with self.assertRaises(OSError):self.t.apply()
        self.assertEqual(self.t.status()['installed'],self.t.originals)
    def test_corrupted_staging_copy_rejected_and_temp_removed(self):
        import shutil
        copy=shutil.copyfile
        def corrupt(source,dest,*a,**kw):
            result=copy(source,dest,*a,**kw)
            if '.naraka-unlocker-' in str(dest):Path(dest).write_bytes(b'bad stage')
            return result
        with patch('body_alias_trial.shutil.copyfile',side_effect=corrupt):
            with self.assertRaisesRegex(RuntimeError,'Staged file'):self.t.apply()
        self.assertEqual(self.t.status()['installed'],self.t.originals);self.assertFalse(list(self.t.game.glob('*.tmp')))
    def test_target_changed_during_copy_is_not_overwritten(self):
        import shutil
        copy=shutil.copyfile
        def change(source,dest,*a,**kw):
            result=copy(source,dest,*a,**kw)
            if '.naraka-unlocker-' in str(dest):(self.t.game/'first').write_bytes(b'external update')
            return result
        with patch('body_alias_trial.shutil.copyfile',side_effect=change):
            with self.assertRaisesRegex(RuntimeError,'changed before'):self.t.apply()
        self.assertEqual((self.t.game/'first').read_bytes(),b'external update');self.assertEqual(json.loads(self.t.state_file.read_text())['phase'],'restore-required')
    def test_missing_and_corrupt_backup_stop_recovery(self):
        self.t.apply();state=json.loads(self.t.state_file.read_text());p=self.t.state_dir/'backups'/state['backup_id']/'first';p.write_bytes(b'bad backup')
        with self.assertRaisesRegex(RuntimeError,'backup unavailable'):self.t.restore()
        self.assertEqual(sha_file(self.t.game/'first'),self.t.candidates['first'])
    def test_bad_backup_identity_rejected(self):
        self.t.apply();state=json.loads(self.t.state_file.read_text());state['backup_id']='../outside';self.t.save(state)
        with self.assertRaisesRegex(ValueError,'backup identity'):self.t.restore()
    def test_unknown_installed_bytes_block_initial_apply(self):
        (self.t.game/'first').write_bytes(b'unknown')
        with self.assertRaisesRegex(RuntimeError,'differ'):self.t.apply()
        self.assertFalse(self.t.state_file.exists())
    def test_unresolved_transaction_cannot_be_reused(self):
        self.t.apply()
        with self.assertRaises(RuntimeError):self.t.apply()
    def test_repeated_apply_restore_cycles(self):
        for _ in range(3):self.t.apply();self.t.restore();self.assertEqual(self.t.status()['installed'],self.t.originals)
    def test_paths_and_index_order_rejected(self):
        for paths in [{'../escape':'x','AppRes.info':'x'},{'C:/escape':'x','AppRes.info':'x'},{'AppRes.info':'x','first':'x'}]:
            with self.assertRaises(ValueError):Trial(self.t.game,self.t.candidate,self.root/'bad',paths,paths,check_closed=lambda:None)
    def test_profile_commit_failure_leaves_recoverable_pending_state(self):
        self.t.apply();state=self.root/'state';state.mkdir();old_profile={'selections':[],'expected':self.t.originals};save_json(state/'profile.json',old_profile)
        pending={'candidate':str(self.t.candidate),'transaction':str(self.t.state_dir),'originals':self.t.originals,'candidates':self.t.candidates,'old_profile':old_profile};save_json(state/'pending.json',pending);(state/'operation.lock').write_text('stale lock')
        e=Engine.__new__(Engine);e.state=state;e.game=self.t.game;e.disk=old_profile;e.pending=pending;e.mutex=threading.Lock();e.read=lambda name,default=None:json.loads((state/name).read_text()) if (state/name).exists() else default
        with patch('core.ensure_closed',lambda:None),patch('core.Trial',lambda *a:Trial(*a,check_closed=lambda:None)):e.recover()
        self.assertEqual(e.disk,old_profile);self.assertFalse((state/'pending.json').exists());self.assertFalse((state/'operation.lock').exists());self.assertEqual(self.t.status()['installed'],self.t.originals)

if __name__=='__main__':unittest.main(verbosity=2)
