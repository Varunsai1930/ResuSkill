import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from helpers import IsolatedHome, fixture
from resuskill_core import jobs, letters, migration, package, profile, store, track, render
from resuskill_core.util import ResuError


class LetterTests(IsolatedHome):
    def setUp(self):
        super().setUp()
        self.jid = self.seed()
        self.target = tempfile.TemporaryDirectory()
        self.addCleanup(self.target.cleanup)
        migrated = Path(self.target.name) / 'v2'
        migration.migrate(migrated)
        os.environ['RESUSKILL_HOME'] = str(migrated)
        package.propose_resume(self.jid, fixture('proposal_good.json'))
        package.accept_resume(self.jid)

    def data(self):
        return {'paragraphs': [{'text': profile.load()['summary'], 'sources': ['summary']}]}

    def state(self):
        return package.review_state(jobs.load(self.jid), package.load(self.jid), profile.load())

    def test_propose_accept_approve_pending_edit_stale_submit_immutable(self):
        package.approve(self.jid)
        letters.propose(self.jid, self.data())
        self.assertEqual(self.state(), 'approved')
        self.assertIsNone(package.load(self.jid).get('letter'))
        letters.accept(self.jid)
        self.assertEqual(self.state(), 'stale')
        package.approve(self.jid)
        letters.propose(self.jid, dict(self.data(), closing='discussion'))
        self.assertEqual(self.state(), 'approved')
        letters.accept(self.jid)
        self.assertEqual(self.state(), 'stale')
        package.approve(self.jid)
        track.set_status(self.jid, 'applied')
        snapshot = store.job_dir(self.jid) / 'snapshots' / jobs.load(self.jid)['tracking']['snapshot']
        before = {p.name: p.read_bytes() for p in snapshot.iterdir()}
        self.assertIn('letter.html', before)
        self.assertIn('letter', store.read_json(snapshot / 'package.json')['package'])
        letters.remove(self.jid)
        self.assertEqual(self.state(), 'stale')
        self.assertEqual(before, {p.name: p.read_bytes() for p in snapshot.iterdir()})

    def test_changed_sources_block_export_and_reapproval(self):
        letters.propose(self.jid, self.data())
        letters.accept(self.jid)
        package.approve(self.jid)
        prof = profile.load()
        prof['summary'] += ' Updated.'
        profile.save(prof)
        self.assertEqual(self.state(), 'stale')
        with self.assertRaises(ResuError):
            package.approve(self.jid)
        with self.assertRaises(ResuError):
            letters.export(self.jid, Path(self.target.name) / 'export')
        self.assertFalse((Path(self.target.name) / 'export').exists())

    def test_invalid_proposal_preserves_accepted_and_previous_draft(self):
        good = letters.propose(self.jid, self.data())
        for data in ({'paragraphs': []}, {'paragraphs': [{'text': 'Created 999 products', 'sources': ['summary']}]},
                     {'paragraphs': [{'text': 'Hello', 'sources': []}]}, dict(self.data(), opening='We lead the market')):
            with self.subTest(data=data), self.assertRaises(ResuError):
                letters.propose(self.jid, data)
            self.assertEqual(package.load(self.jid)['letter_proposal'], good)

    def test_html_escaping_and_pdf_failure_cleanup(self):
        prof = profile.load()
        prof['summary'] = '<script>alert("test")</script> multilingual 日本語'
        profile.save(prof)
        letters.propose(self.jid, self.data())
        letters.accept(self.jid)
        target = Path(self.target.name) / 'html'
        letters.export(self.jid, target)
        html = (target / 'letter.html').read_text()
        self.assertNotIn('<script>', html)
        self.assertIn('日本語', html)
        before = (target / 'letter.html').read_bytes()
        with self.assertRaises(ResuError):
            letters.export(self.jid, target)
        self.assertEqual(before, (target / 'letter.html').read_bytes())
        failed = Path(self.target.name) / 'failed'
        with patch.object(render, 'print_pdf', side_effect=ResuError('no browser')), self.assertRaises(ResuError):
            letters.export(self.jid, failed, True)
        self.assertFalse(failed.exists())
        self.assertEqual(list(Path(self.target.name).glob('.letter-*')), [])

    def test_snapshot_failure_does_not_record_submission(self):
        letters.propose(self.jid, self.data())
        letters.accept(self.jid)
        package.approve(self.jid)
        with patch('resuskill_core.track.shutil.copy2', side_effect=OSError('injected')), self.assertRaises(OSError):
            track.set_status(self.jid, 'applied')
        self.assertEqual(jobs.load(self.jid)['tracking']['status'], 'saved')
        self.assertEqual(list((store.job_dir(self.jid) / 'snapshots').iterdir()), [])

    def test_resume_only_still_works(self):
        package.approve(self.jid)
        self.assertEqual(self.state(), 'approved')
        self.assertNotIn('letter', package.resolved(jobs.load(self.jid), profile.load(), package.load(self.jid)))

    def test_retired_evidence_stales_accepted_letter(self):
        import subprocess
        from resuskill_core import ledger
        repo = Path(self.target.name) / 'repo'
        repo.mkdir()
        def git(*args):
            return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()
        git('init')
        git('config', 'user.email', 'fictional@example.com')
        git('config', 'user.name', 'Fixture')
        (repo / 'code.txt').write_text('addition function\n')
        git('add', '.')
        git('commit', '-m', 'fixture')
        entry = profile.load()['projects'][0]
        row = ledger.propose({'repository': str(repo), 'commit': git('rev-parse', 'HEAD'), 'path': 'code.txt',
                              'start_line': 1, 'end_line': 1, 'excerpt': 'addition function',
                              'observed_fact': 'An addition function.', 'project_id': entry['id'],
                              'bullet_id': entry['bullets'][0]['id'], 'contribution': 'I wrote the addition function.', 'outcome': ''})
        data = {'paragraphs': [{'text': 'I wrote the addition function.', 'sources': [row['id']]}]}
        with self.assertRaises(ResuError):
            letters.propose(self.jid, data)
        ledger.action(row['id'], 'confirm')
        letters.propose(self.jid, data)
        letters.accept(self.jid)
        package.approve(self.jid)
        ledger.action(row['id'], 'retire')
        self.assertEqual(self.state(), 'stale')
        with self.assertRaises(ResuError):
            package.approve(self.jid)
        with self.assertRaises(ResuError):
            letters.export(self.jid, Path(self.target.name) / 'stale')

    def test_incomplete_stored_letter_has_actionable_error(self):
        from copy import deepcopy
        letters.propose(self.jid, self.data())
        letters.accept(self.jid)
        original = package.load(self.jid)
        for mutation in ('opening', 'paragraph'):
            pkg = deepcopy(original)
            if mutation == 'opening':
                del pkg['letter']['content']['opening']
            else:
                pkg['letter']['content']['paragraphs'] = [{}]
            store.write_json(store.job_dir(self.jid) / 'package.json', pkg)
            with self.subTest(mutation=mutation), self.assertRaises(ResuError):
                letters.export(self.jid, Path(self.target.name) / 'damaged')
            with self.assertRaises(ResuError):
                render.render(self.jid)
