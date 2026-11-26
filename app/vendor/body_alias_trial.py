"""Review/status/apply/restore for the experimental two-file body-alias trial.

No installation changes occur for status or self-test. Apply/restore require
Naraka and its launcher closed. This never launches the game, stops a process,
alters protection, injects code or updates ownership. Use only after approving
the concrete native-acceptance trial described in FILE_INTEGRATION_PROGRESS.md.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
GAME = Path(os.environ.get("NARAKA_STREAMING_ASSETS", "NARAKA_STREAMING_ASSETS"))
FILES = ('6/1/61f5d992abed2fb8', 'AppRes.info')


def sha_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def ensure_closed():
    # Keep a fresh check at every existing transaction boundary, without
    # launching a PowerShell interpreter for each individual file.
    from process_guard import ensure_closed as check
    check()


class Trial:
    def __init__(self, game, candidate, state_dir, originals, candidates, check_closed=ensure_closed):
        self.game = game.resolve()
        self.candidate = candidate.resolve()
        self.state_dir = state_dir.resolve()
        self.originals = originals
        self.candidates = candidates
        self.files = tuple(originals)
        if set(originals) != set(candidates) or not self.files or self.files[-1] != 'AppRes.info':
            raise ValueError('Trial identities must cover identical files with AppRes.info last')
        for name in self.files:
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError('Trial path is not installation-relative')
            if not (self.candidate / name).resolve().is_relative_to(self.candidate):
                raise ValueError('Candidate path escapes expected directory')
        self.check_closed = check_closed
        self.progress = lambda phase,n,total,name: None
        self.state_file = self.state_dir / 'state.json'

    def installed(self, relative):
        if relative not in self.files:
            raise ValueError('Unexpected trial file')
        path = (self.game / relative).resolve()
        if not path.is_relative_to(self.game):
            raise ValueError('Installed path escapes expected game directory')
        return path

    def save(self, state):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temp = self.state_dir / ('state-' + uuid.uuid4().hex + '.tmp')
        temp.write_text(json.dumps(state, indent=2), encoding='utf-8')
        os.replace(temp, self.state_file)

    def replace(self, source, relative, expected_current, expected_new):
        self.check_closed()
        target = self.installed(relative)
        if sha_file(target) != expected_current or sha_file(source) != expected_new:
            raise RuntimeError('File identity changed; refusing replacement: ' + relative)
        temp = target.with_name(target.name + '.naraka-unlocker-' + uuid.uuid4().hex + '.tmp')
        if not temp.resolve().is_relative_to(self.game):
            raise ValueError('Staging path escapes expected directory')
        try:
            shutil.copyfile(source, temp)
            if sha_file(temp) != expected_new:
                raise RuntimeError('Staged file hash mismatch')
            self.check_closed()
            if sha_file(target) != expected_current:
                raise RuntimeError('Installed file changed before replacement')
            os.replace(temp, target)
        finally:
            if temp.exists():
                temp.unlink()

    def status(self):
        return {'installed': {name: sha_file(self.installed(name)) for name in self.files},
                'expected_original': self.originals,
                'candidate': {name: sha_file(self.candidate / name) for name in self.files},
                'transaction': json.loads(self.state_file.read_text()) if self.state_file.exists() else None}

    def apply(self):
        self.check_closed()
        before = self.status()
        if before['installed'] != self.originals:
            raise RuntimeError('Installed files differ from reviewed originals; refusing trial')
        if before['candidate'] != self.candidates:
            raise RuntimeError('Candidate files differ from reviewed identities; refusing trial')
        if before['transaction'] and before['transaction']['phase'] != 'restored':
            raise RuntimeError('Existing unresolved trial transaction; inspect/restore it first')
        run_id = uuid.uuid4().hex
        backup = self.state_dir / 'backups' / run_id
        if not backup.resolve().is_relative_to(self.state_dir):
            raise ValueError('Backup path escapes state directory')
        state = {'phase': 'backing-up', 'backup_id': run_id,
                 'originals': self.originals, 'candidate': before['candidate'], 'written': []}
        self.save(state)
        for n,name in enumerate(self.files,1):
            target = backup / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.installed(name), target)
            if sha_file(target) != self.originals[name]:
                raise RuntimeError('Backup verification failed before installation changes')
            self.progress('backup',n,len(self.files),name)
        state['phase'] = 'backups-verified'
        self.save(state)
        try:
            for n,name in enumerate(self.files,1):
                self.replace(self.candidate / name, name, self.originals[name], state['candidate'][name])
                state['written'].append(name)
                state['phase'] = 'applying'
                self.save(state)
                self.progress('write',n,len(self.files),name)
            state['phase'] = 'applied-experimental'
            self.save(state)
        except Exception as exc:
            state['apply_error'] = str(exc)
            try:
                self.save(state)
            except OSError:
                pass
            try:
                self.restore()
            except Exception as restore_exc:
                state['phase'] = 'restore-required'
                state['restore_error'] = str(restore_exc)
                try:
                    self.save(state)
                except OSError:
                    pass
            raise
        return self.status()

    def restore(self):
        self.check_closed()
        if not self.state_file.exists():
            raise RuntimeError('No trial transaction to restore')
        state = json.loads(self.state_file.read_text())
        if state['originals'] != self.originals:
            raise RuntimeError('Transaction original identities differ from reviewed build')
        run_id = state['backup_id']
        if len(run_id) != 32 or any(c not in '0123456789abcdef' for c in run_id):
            raise ValueError('Invalid backup identity')
        backup = (self.state_dir / 'backups' / run_id).resolve()
        if not backup.is_relative_to(self.state_dir):
            raise ValueError('Backup resolves outside state directory')
        # Restore the index first, then the body bundle. Never overwrite a game
        # update or third-party change that differs from both known identities.
        for name in reversed(self.files):
            current = sha_file(self.installed(name))
            if current == self.originals[name]:
                continue
            if current != state['candidate'][name]:
                raise RuntimeError('Installed file differs from original and trial; refusing overwrite: ' + name)
            source = (backup / name).resolve()
            if not source.is_relative_to(backup) or sha_file(source) != self.originals[name]:
                raise RuntimeError('Verified original backup unavailable')
            self.replace(source, name, current, self.originals[name])
        state['phase'] = 'restored'
        self.save(state)
        return self.status()


def self_test():
    base = ROOT / 'work' / ('trial-manager-self-test-' + uuid.uuid4().hex)
    game, candidate, state = (base / name for name in ('mock-game', 'candidate', 'state'))
    originals = {}
    for name in FILES:
        a, b = game / name, candidate / name
        a.parent.mkdir(parents=True, exist_ok=True)
        b.parent.mkdir(parents=True, exist_ok=True)
        a.write_bytes(('original:' + name).encode())
        b.write_bytes(('candidate:' + name).encode())
        originals[name] = sha_file(a)
    candidates = {name: sha_file(candidate / name) for name in FILES}
    t = Trial(game, candidate, state, originals, candidates, check_closed=lambda: None)
    assert t.apply()['transaction']['phase'] == 'applied-experimental'
    assert t.restore()['installed'] == originals
    real_replace = t.replace
    calls = [0]
    def interrupted(source, relative, expected_current, expected_new):
        calls[0] += 1
        if calls[0] == 2:
            raise OSError('simulated second-file failure')
        return real_replace(source, relative, expected_current, expected_new)
    t.replace = interrupted
    try:
        t.apply()
    except OSError:
        assert t.status()['installed'] == originals
        assert t.status()['transaction']['phase'] == 'restored'
    else:
        raise AssertionError('Expected interrupted apply')
    t.replace = real_replace
    t.apply()
    conflict = game / FILES[0]
    conflict.write_bytes(b'simulated-third-party-update')
    try:
        t.restore()
    except RuntimeError:
        assert conflict.read_bytes() == b'simulated-third-party-update'
    else:
        raise AssertionError('Restore overwrote unknown file identity')
    def blocked():
        raise RuntimeError('simulated running game')
    blocked_trial = Trial(game, candidate, base / 'blocked-state', originals, candidates, check_closed=blocked)
    try:
        blocked_trial.apply()
    except RuntimeError:
        assert not blocked_trial.state_file.exists()
    else:
        raise AssertionError('Apply ignored closed-game gate')
    result = {'scope': 'mock installation inside project work only', 'real_game_modified': False,
              'apply_and_restore_verified': True, 'unknown_file_preserved': True,
              'partial_apply_rolled_back': True,
              'running_game_gate_prevented_write': True, 'mock_location': str(base)}
    (ROOT / 'reports/body-alias-trial-manager-self-test.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('status', 'self-test', 'apply', 'restore'))
    a = p.parse_args()
    if a.action == 'self-test':
        result = self_test()
    else:
        report = json.loads((ROOT / 'reports/body-alias-index-candidate.json').read_text())
        bundle_report = json.loads((ROOT / 'reports/body-alias-candidate.json').read_text())
        originals = {FILES[0]: bundle_report['original_file_sha256'], FILES[1]: report['original_index_sha256']}
        candidates = {FILES[0]: bundle_report['candidate_sha256'], FILES[1]: report['candidate_index_sha256']}
        candidate_dir = Path(report['candidate_layout']).resolve()
        if candidate_dir != (ROOT / 'work/body-alias-candidate/StreamingAssets').resolve():
            raise ValueError('Candidate directory differs from fixed project trial layout')
        trial = Trial(GAME, candidate_dir, ROOT / 'work/body-alias-trial', originals, candidates)
        if a.action == 'status':
            result = trial.status()
        else:
            trial.state_dir.mkdir(parents=True, exist_ok=True)
            lock_path = trial.state_dir / 'operation.lock'
            with lock_path.open('x') as lock:
                try:
                    lock.write(str(os.getpid()))
                    lock.flush()
                    result = getattr(trial, a.action)()
                finally:
                    lock.close()
                    lock_path.unlink()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
