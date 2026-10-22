import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from helpers import IsolatedHome
from resuskill_core import ledger, migration, profile, store, jobs, package
from resuskill_core.util import ResuError


class LedgerTests(IsolatedHome):
    def setUp(self):
        super().setUp()
        self.jid = self.seed()
        self.workspace = tempfile.TemporaryDirectory(prefix='evidence fixture ')
        self.addCleanup(self.workspace.cleanup)
        self.repo = Path(self.workspace.name) / 'repo'
        self.repo.mkdir()
        self.git('init')
        self.git('config', 'user.email', 'fictional@example.com')
        self.git('config', 'user.name', 'Fixture')
        (self.repo / 'code.py').write_text('def add(a, b):\n    return a + b\n')
        (self.repo / 'binary').write_bytes(b'\x00\x01')
        self.git('add', '.')
        self.git('commit', '-m', 'fixture')
        self.commit = self.git('rev-parse', 'HEAD').strip()
        self.target = Path(self.workspace.name) / 'data-v2'
        migration.migrate(self.target)
        os.environ['RESUSKILL_HOME'] = str(self.target)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True, text=True).stdout

    def evidence(self):
        entry = profile.load()['projects'][0]
        return {'repository': str(self.repo), 'commit': self.commit, 'path': 'code.py',
                'start_line': 1, 'end_line': 2, 'excerpt': 'def add(a, b):\n    return a + b',
                'observed_fact': 'Defines an addition function.', 'project_id': entry['id'],
                'bullet_id': entry['bullets'][0]['id'], 'contribution': 'I wrote the addition function.', 'outcome': ''}

    def test_proposal_confirmation_retirement_and_uncommitted_changes(self):
        row = ledger.propose(self.evidence())
        with self.assertRaises(ResuError):
            ledger.resolve([row['id']])
        ledger.action(row['id'], 'confirm')
        (self.repo / 'code.py').write_text('uncommitted text')
        self.assertEqual(ledger.resolve([row['id']])[0]['state'], 'confirmed')
        self.git('add', '.')
        self.git('commit', '-m', 'branch moved')
        self.assertEqual(ledger.check(row['id'])[0]['state'], 'verified')
        ledger.action(row['id'], 'retire')
        with self.assertRaises(ResuError):
            ledger.resolve([row['id']])
        self.assertEqual(len(ledger.load()['records']), 1)

    def test_missing_file_commit_range_binary_and_wrong_excerpt(self):
        for changes in ({'commit': 'HEAD'}, {'commit': '0' * 40}, {'path': '../code.py'},
                        {'path': 'missing'}, {'end_line': 9}, {'start_line': 0},
                        {'path': 'binary'}, {'excerpt': 'different'}, {'start_line': True}):
            with self.subTest(changes=changes), self.assertRaises(ResuError):
                ledger.propose(dict(self.evidence(), **changes))
        self.assertEqual(ledger.load()['records'], [])

    def test_link_change_and_temporary_unavailability_are_distinct(self):
        row = ledger.propose(self.evidence())
        ledger.action(row['id'], 'confirm')
        moved = self.repo.with_name('away')
        self.repo.rename(moved)
        self.assertEqual(ledger.check(row['id'])[0]['state'], 'unavailable')
        self.assertEqual(ledger.load()['records'][0]['state'], 'confirmed')
        moved.rename(self.repo)
        prof = profile.load()
        prof['projects'][0]['bullets'][0]['text'] += ' Changed'
        profile.save(prof)
        self.assertEqual(ledger.check(row['id'])[0]['state'], 'needs_review')
        with self.assertRaises(ResuError):
            ledger.resolve([row['id']])

    def test_changed_citation_and_corrupt_structure_refused(self):
        row = ledger.propose(self.evidence())
        ledger.action(row['id'], 'confirm')
        data = ledger.load()
        data['records'][0]['evidence']['contribution'] = 'I led the team'
        ledger.save(data)
        self.assertEqual(ledger.check(row['id'])[0]['state'], 'needs_review')
        data['records'][0]['evidence'] = []
        ledger.save(data)
        with self.assertRaises(ResuError):
            ledger.load()

    def test_symlink_and_submodule_modes_refused(self):
        blob = self.git('rev-parse', self.commit + ':code.py').strip()
        self.git('update-index', '--add', '--cacheinfo', '120000,' + blob + ',link')
        self.git('update-index', '--add', '--cacheinfo', '160000,' + self.commit + ',module')
        self.git('commit', '-m', 'unsupported types')
        commit = self.git('rev-parse', 'HEAD').strip()
        for path in ('link', 'module'):
            with self.subTest(path=path), self.assertRaises(ResuError):
                ledger.propose(dict(self.evidence(), commit=commit, path=path))


class MigrationTests(IsolatedHome):
    def test_copy_preserves_original_snapshots_and_invalidates_approval(self):
        jid = self.seed()
        pkg = package.load(jid)
        pkg['approval'] = {'profile_revision': 1, 'job_revision': 1, 'hash': 'old'}
        package.save(jid, pkg, content_changed=False)
        frozen = store.job_dir(jid) / 'snapshots' / 'old.json'
        frozen.parent.mkdir()
        frozen.write_text('{"historical": true}')
        before = {str(p.relative_to(store.home())): p.read_bytes() for p in store.home().rglob('*') if p.is_file()}
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'copy'
            migration.migrate(target)
            self.assertEqual(before, {str(p.relative_to(store.home())): p.read_bytes() for p in store.home().rglob('*') if p.is_file()})
            self.assertEqual((target / frozen.relative_to(store.home())).read_bytes(), frozen.read_bytes())
            with patch.dict(os.environ, RESUSKILL_HOME=str(target)):
                self.assertEqual(store.data_version(), 2)
                self.assertIsNone(package.load(jid)['approval'])
                self.assertEqual(jobs.load(jid)['schema_version'], 2)
                profile.save(profile.load())
            with self.assertRaises(ResuError):
                migration.migrate(target)

    def test_failure_leaves_source_and_destination_untouched(self):
        self.seed()
        original = store.profile_path().read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'copy'
            with patch.object(store, 'write_json', side_effect=OSError('injected')), self.assertRaises(OSError):
                migration.migrate(target)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(folder).iterdir()), [])
        self.assertEqual(store.profile_path().read_bytes(), original)
        self.assertEqual(store.data_version(), 1)
        with self.assertRaises(ResuError):
            ledger.load()

    def test_unfinished_import_blocks_migration(self):
        from resuskill_core import imports
        self.seed()
        data = [{'company': 'Example', 'title': 'Role', 'description': 'Python',
                 'source_url': 'https://example.com/1', 'observed_at': '2026-01-01T00:00:00Z'}]
        preview = imports.preview(data)
        real = store.write_json
        def interrupted(path, value):
            if Path(path).name == 'job.json':
                raise OSError('injected')
            real(path, value)
        with patch.object(store, 'write_json', side_effect=interrupted), self.assertRaises(OSError):
            imports.apply(data, preview, [1])
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'copy'
            with self.assertRaisesRegex(ResuError, 'incomplete imports'):
                migration.migrate(target)
            self.assertFalse(target.exists())
            imports.apply(data, preview, [1])
            migration.migrate(target)
            self.assertTrue(target.exists())
