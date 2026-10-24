from copy import deepcopy
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from helpers import IsolatedHome, fixture
from resuskill_core import cli, jobs, ledger, migration, package, profile, store, stories
from resuskill_core.util import ResuError


class StoryTests(IsolatedHome):
    def setUp(self):
        super().setUp()
        self.jid = self.seed()
        self.work = tempfile.TemporaryDirectory(prefix='story tests ')
        self.addCleanup(self.work.cleanup)
        migrated = Path(self.work.name) / 'data'
        migration.migrate(migrated)
        os.environ['RESUSKILL_HOME'] = str(migrated)

    def data(self):
        bullet = profile.load()['projects'][0]['bullets'][0]
        part = {'text': bullet['text'], 'sources': [bullet['id']]}
        return {'situation': deepcopy(part), 'task': deepcopy(part), 'action': deepcopy(part),
                'result': None, 'contribution_scope': 'shared'}

    def accepted(self):
        row = stories.propose(self.data())
        stories.accept(row['id'])
        return row['id']

    def test_unknown_result_and_pending_replacement_preserve_accepted(self):
        ident = self.accepted()
        before = stories.show(ident)
        self.assertIsNone(before['record']['content']['result'])
        data = self.data()
        data['contribution_scope'] = 'personal'
        stories.propose(data, ident)
        self.assertEqual(stories.show(ident), before)
        self.assertEqual(stories.show(ident, True)['state'], 'proposed')
        stories.accept(ident)
        self.assertEqual(stories.show(ident)['record']['content']['contribution_scope'], 'personal')

    def test_invalid_results_and_missing_required_parts_preserve_library(self):
        self.accepted()
        before = (store.home() / 'stories.json').read_bytes()
        for replacement in ({'result': {'text': 'Saved 999 hours', 'sources': ['summary']}},
                            {'action': {}}, {'result': {'text': 'Success', 'sources': []}},
                            {'contribution_scope': 'everyone'}):
            with self.subTest(replacement=replacement), self.assertRaises(ResuError):
                stories.propose(dict(self.data(), **replacement))
            self.assertEqual(before, (store.home() / 'stories.json').read_bytes())
        data = self.data()
        del data['result']
        with self.assertRaises(ResuError):
            stories.propose(data)

    def test_story_changes_do_not_modify_application_approval(self):
        package.propose_resume(self.jid, fixture('proposal_good.json'))
        package.accept_resume(self.jid)
        package.approve(self.jid)
        before = (store.job_dir(self.jid) / 'package.json').read_bytes()
        ident = self.accepted()
        stories.propose(self.data(), ident)
        stories.accept(ident)
        self.assertEqual(before, (store.job_dir(self.jid) / 'package.json').read_bytes())
        self.assertEqual(package.review_state(jobs.load(self.jid), package.load(self.jid), profile.load()), 'approved')

    def test_changed_source_stales_story_and_excludes_suggestions(self):
        ident = self.accepted()
        suggested = stories.suggest(self.jid)
        self.assertEqual(suggested[0]['id'], ident)
        self.assertEqual(suggested[0]['basis'][0]['requirement'], 'r1')
        self.assertIn('python', suggested[0]['basis'][0]['skills'])
        prof = profile.load()
        prof['projects'][0]['bullets'][0]['text'] += ' changed'
        profile.save(prof)
        self.assertEqual(stories.show(ident)['state'], 'stale')
        self.assertEqual(stories.suggest(self.jid), [])
        with self.assertRaises(ResuError):
            stories.export(ident, Path(self.work.name) / 'stale')

    def test_suggestions_require_reviewed_requirements_and_confirmed_skills(self):
        self.accepted()
        job = jobs.add('Other', 'Role', 'Python')
        with self.assertRaises(ResuError):
            stories.suggest(job['id'])
        prof = profile.load()
        prof['skills'] = []
        profile.save(prof)
        self.assertEqual(stories.suggest(self.jid), [])

    def test_export_escaping_and_failure_cleanup(self):
        prof = profile.load()
        prof['projects'][0]['bullets'][0]['text'] = '<script>alert("test")</script> 日本語'
        profile.save(prof)
        ident = self.accepted()
        output = Path(self.work.name) / 'export'
        stories.export(ident, output)
        html = (output / 'story.html').read_text(encoding='utf-8')
        self.assertNotIn('<script>', html)
        self.assertIn('Result unknown', html)
        self.assertIn('日本語', html)
        with self.assertRaises(ResuError):
            stories.export(ident, output)
        failed = Path(self.work.name) / 'failed'
        with patch.object(store, 'write_json', side_effect=OSError('injected')), self.assertRaises(OSError):
            stories.export(ident, failed)
        self.assertFalse(failed.exists())
        self.assertEqual(list(Path(self.work.name).glob('.story-*')), [])

    def test_corrupt_stored_shapes_and_duplicate_ids_refused(self):
        self.accepted()
        original = stories.load()
        for mode in ('duplicate', 'action', 'version'):
            data = deepcopy(original)
            if mode == 'duplicate':
                data['records'].append(deepcopy(data['records'][0]))
            elif mode == 'action':
                data['records'][0]['accepted']['content']['action'] = {}
            else:
                data['version'] = True
            stories.save(data)
            with self.subTest(mode=mode), self.assertRaises(ResuError):
                stories.check()

    def test_implementation_questions_only_from_current_confirmed_evidence(self):
        repo = Path(self.work.name) / 'repo'
        repo.mkdir()
        def git(*args):
            return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()
        git('init')
        git('config', 'user.email', 'fictional@example.com')
        git('config', 'user.name', 'Fixture')
        (repo / 'code.txt').write_text('return value\n')
        git('add', '.')
        git('commit', '-m', 'fixture')
        entry = profile.load()['projects'][0]
        row = ledger.propose({'repository': str(repo), 'commit': git('rev-parse', 'HEAD'), 'path': 'code.txt',
                              'start_line': 1, 'end_line': 1, 'excerpt': 'return value',
                              'observed_fact': 'Returns a value.', 'project_id': entry['id'], 'bullet_id': entry['bullets'][0]['id'],
                              'contribution': 'I wrote the function.', 'outcome': ''})
        data = self.data()
        data['action'] = {'text': 'I wrote the function.', 'sources': [row['id']]}
        with self.assertRaises(ResuError):
            stories.propose(data)
        ledger.action(row['id'], 'confirm')
        ident = stories.propose(data)['id']
        stories.accept(ident)
        question = stories.show(ident)['implementation_questions'][0]
        self.assertEqual(question['excerpt'], 'return value')
        self.assertEqual(question['commit'], row['evidence']['commit'])
        ledger.action(row['id'], 'retire')
        self.assertEqual(stories.show(ident)['state'], 'stale')
        self.assertEqual(stories.show(ident)['implementation_questions'], [])
