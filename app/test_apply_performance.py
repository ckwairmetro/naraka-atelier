import copy,ctypes,json,sys,tempfile,time,types,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'vendor'))
import native_edit,bundle_editor
from native_edit import CommonEditor
from bundle_editor import CabEditor
import process_guard

class TableCacheTests(unittest.TestCase):
    def editor(self):
        e=CommonEditor.__new__(CommonEditor);e._section_cache={};e.tables={'A':[None,None,b'old'],'B':[None,None,b'other']};e.table=lambda name:e.tables[name];e.decoder=types.SimpleNamespace(row=lambda sec,raw:{'value':raw.decode(),'mutable':[]});return e
    def test_parsing_reused_but_decoded_results_are_private(self):
        e=self.editor()
        with patch('native_edit.section_rows',return_value=({},[],{1:b'abc'})) as parse:
            first=e.get('A','sec',1);first['mutable'].append(1);second=e.get('A','sec',1)
        self.assertEqual(parse.call_count,1);self.assertEqual(second['mutable'],[])
    def test_replacement_with_same_length_invalidates_cache(self):
        e=self.editor()
        with patch('native_edit.section_rows',side_effect=lambda data,s:({},[],{1:data})) as parse:
            self.assertEqual(e.get('A','sec',1)['value'],'old');e.tables['A'][2]=b'new';self.assertEqual(e.get('A','sec',1)['value'],'new')
        self.assertEqual(parse.call_count,2)
    def test_table_section_and_instance_isolation(self):
        e=self.editor();other=self.editor()
        with patch('native_edit.section_rows',side_effect=lambda data,s:({},[],{1:data+s.encode()})) as parse:
            e.get('A','one',1);e.get('A','two',1);e.get('B','one',1);other.get('A','one',1);e.get('A','one',1)
        self.assertEqual(parse.call_count,4)
    def test_appended_and_removed_rows_refresh(self):
        e=self.editor()
        with patch('native_edit.section_rows',side_effect=lambda data,s:({},[],{1:b'a',**({2:b'b'} if data==b'new' else {})})):
            e.get('A','sec',1);e.tables['A'][2]=b'new';self.assertEqual(e.get('A','sec',2)['value'],'b');e.tables['A'][2]=b'old'
            with self.assertRaises(KeyError):e.get('A','sec',2)
    def test_failed_parse_is_not_cached(self):
        e=self.editor()
        with patch('native_edit.section_rows',side_effect=[ValueError('bad'),({},[],{1:b'ok'})]):
            with self.assertRaises(ValueError):e.get('A','sec',1)
            self.assertEqual(e.get('A','sec',1)['value'],'ok')
    def test_mutable_buffer_is_never_cached(self):
        e=self.editor();e.tables['A'][2]=bytearray(b'old')
        with patch('native_edit.section_rows',side_effect=lambda data,s:({},[],{1:bytes(data)})) as parse:
            self.assertEqual(e.get('A','sec',1)['value'],'old');e.tables['A'][2][:]=b'new';self.assertEqual(e.get('A','sec',1)['value'],'new')
        self.assertEqual(parse.call_count,2)

class ContainerCacheTests(unittest.TestCase):
    def cab(self):
        c=CabEditor.__new__(CabEditor);c.abobj=types.SimpleNamespace(path_id=12);c.trees={12:{'m_Container':[('path',{'asset':{'m_PathID':44,'m_FileID':0}})]}};c.payloads={};c.opaque_tails={};c._container_cache=None
        obj=types.SimpleNamespace(save_typetree=lambda t:b'raw',serialized_type=types.SimpleNamespace(node=None));c.sf=types.SimpleNamespace(objects={12:obj});return c
    def test_lookup_and_inventory_cannot_mutate_cache(self):
        c=self.cab();c.entry('path')['asset']['m_PathID']=123;c.entries()['path']['asset']['m_PathID']=456;self.assertEqual(c.entry('path')['asset']['m_PathID'],44);self.assertIsNone(c.entry('missing'))
    def test_put_invalidates_lookup(self):
        c=self.cab();c.entry('path');value={'m_Container':[('path',{'asset':{'m_PathID':99,'m_FileID':0}})]}
        with patch('bundle_editor.read_typetree',return_value=value):c.put(12,value)
        self.assertEqual(c.entry('path')['asset']['m_PathID'],99)
    def test_no_assetbundle_is_empty(self):
        c=self.cab();c.abobj=None;self.assertEqual(c.entries(),{});self.assertIsNone(c.entry('path'))

class FakeApi:
    def __init__(self,names=(),first_error=18,next_error=18,snapshot=45,close=True):self.names=list(names);self.first_error=first_error;self.next_error=next_error;self.snapshot=snapshot;self.close=close;self.closed=0
    def CreateToolhelp32Snapshot(self,*args):return self.snapshot
    def write(self,entry):ctypes.cast(entry,ctypes.POINTER(process_guard.PROCESSENTRY32W)).contents.szExeFile=self.names.pop(0);return 1
    def Process32FirstW(self,snapshot,entry):
        if self.names:return self.write(entry)
        ctypes.set_last_error(self.first_error);return 0
    def Process32NextW(self,snapshot,entry):
        if self.names:return self.write(entry)
        ctypes.set_last_error(self.next_error);return 0
    def CloseHandle(self,*args):self.closed+=1;return self.close

class GuardTests(unittest.TestCase):
    def test_normal_enumeration_and_case(self):
        api=FakeApi(['System','NarakaBladepoint.EXE','startgame.exe']);self.assertEqual(process_guard.process_names(api),{'system','narakabladepoint.exe','startgame.exe'});self.assertEqual(api.closed,1)
    def test_empty_inventory(self):
        api=FakeApi();self.assertEqual(process_guard.process_names(api),set());self.assertEqual(api.closed,1)
    def test_invalid_snapshot_fails_closed(self):
        for handle in [None,0,ctypes.c_void_p(-1).value]:
            with self.assertRaises(RuntimeError):process_guard.process_names(FakeApi(snapshot=handle))
    def test_partial_or_denied_enumeration_fails_closed(self):
        for api in [FakeApi([],first_error=5),FakeApi(['ordinary.exe'],next_error=5)]:
            with self.assertRaisesRegex(RuntimeError,'incomplete'):process_guard.process_names(api)
            self.assertEqual(api.closed,1)
    def test_handle_close_failure_is_not_ignored(self):
        with self.assertRaisesRegex(RuntimeError,'close'):process_guard.process_names(FakeApi(close=False))
    def test_guard_checks_both_names_and_rescans_every_call(self):
        with patch('process_guard.process_names',side_effect=[set(),{'startgame.exe'},{'narakabladepoint.exe'},set()]) as names:
            process_guard.ensure_closed()
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError,'close it'):process_guard.ensure_closed()
            process_guard.ensure_closed()
        self.assertEqual(names.call_count,4)

    def test_guard_handles_extensionless_and_mixed_case_names(self):
        for name in ['NarakaBladepoint','StartGame','NARAKABLADEPOINT.EXE','STARTGAME.EXE']:
            with patch('process_guard.process_names',return_value={name}):
                with self.assertRaises(RuntimeError):process_guard.ensure_closed()

class TransactionEdgeTests(unittest.TestCase):
    def fixture(self,path,guard=lambda:None):
        from body_alias_trial import Trial,sha_file
        game=path/'game';candidate=path/'candidate';game.mkdir();candidate.mkdir();originals={};after={}
        for name in ['first','second','AppRes.info']:
            (game/name).write_bytes(('original-'+name).encode());(candidate/name).write_bytes(('candidate-'+name).encode());originals[name]=sha_file(game/name);after[name]=sha_file(candidate/name)
        return Trial(game,candidate,path/'state',originals,after,check_closed=guard)
    def test_restart_during_install_preserves_recovery_journal(self):
        from body_alias_trial import sha_file
        with tempfile.TemporaryDirectory() as tmp:
            running=[False]
            def guard():
                if running[0]:raise RuntimeError('game reopened')
            trial=self.fixture(Path(tmp),guard);replace=trial.replace
            def reopen(source,relative,*args):
                replace(source,relative,*args)
                if relative=='first':running[0]=True
            trial.replace=reopen
            with self.assertRaisesRegex(RuntimeError,'reopened'):trial.apply()
            state=json.loads(trial.state_file.read_text());self.assertEqual(state['phase'],'restore-required');self.assertEqual(state['written'],['first']);self.assertEqual(sha_file(trial.game/'AppRes.info'),trial.originals['AppRes.info'])
            running[0]=False;trial.replace=replace;trial.restore();self.assertEqual(trial.status()['installed'],trial.originals)
    def test_backup_failure_prevents_all_resource_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial=self.fixture(Path(tmp));real_copy=__import__('shutil').copyfile
            def copy(source,dest,*a,**k):
                if 'backups' in str(dest):raise OSError('simulated full disk')
                return real_copy(source,dest,*a,**k)
            with patch('body_alias_trial.shutil.copyfile',side_effect=copy):
                with self.assertRaisesRegex(OSError,'full disk'):trial.apply()
            self.assertEqual(trial.status()['installed'],trial.originals)
    def test_candidate_modified_after_initial_validation_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial=self.fixture(Path(tmp));replace=trial.replace
            def corrupt(source,relative,*args):
                if relative=='first':source.write_bytes(b'unknown candidate')
                return replace(source,relative,*args)
            trial.replace=corrupt
            with self.assertRaisesRegex(RuntimeError,'identity changed'):trial.apply()
            self.assertEqual(trial.status()['installed'],trial.originals)

if __name__=='__main__':unittest.main(verbosity=2)
