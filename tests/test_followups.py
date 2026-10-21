import contextlib
import io
import os
from datetime import date
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from helpers import IsolatedHome, ROOT, fixture
from resuskill_core import cli, followups, jobs, package, pipeline, store, track
from resuskill_core.util import ResuError


class FollowupTests(IsolatedHome):
    def test_dates_ids_reschedule_and_finish(self):
        jid = self.seed()
        first = followups.set_followup(jid, '2028-02-29', '<check>')
        second = followups.set_followup(jid, '2028-03-01')
        self.assertEqual((first['id'], second['id']), ('f1', 'f2'))
        followups.set_followup(jid, '2028-03-02', 'new note', 'f1')
        rows = followups.rows(jobs.load(jid), date(2028, 3, 1))
        self.assertEqual([r['timing'] for r in rows], ['due_today', 'upcoming'])
        followups.finish(jid, 'f1', 'completed')
        followups.finish(jid, 'f1', 'completed')
        with self.assertRaises(ResuError):
            followups.set_followup(jid, '2028-03-04', ident='f1')
        self.assertEqual(followups.set_followup(jid, '2028-03-04')['id'], 'f3')
        for invalid in ('2027-02-29', '2028-2-29', '2028-02', '2028-02-29T12:00:00', None):
            with self.subTest(invalid=invalid), self.assertRaises(ResuError):
                followups.set_followup(jid, invalid)

    def test_terminal_and_reopen_do_not_reactivate(self):
        jid = self.seed()
        followups.set_followup(jid, '2000-01-01')
        self.assertEqual(pipeline.report()['jobs'][0]['next_action']['code'], 'followup_due')
        track.set_status(jid, 'rejected')
        self.assertEqual(followups.rows(jobs.load(jid))[0]['state'], 'inactive')
        with self.assertRaises(ResuError):
            followups.set_followup(jid, '2028-01-01')
        track.set_status(jid, 'saved')
        self.assertEqual(followups.rows(jobs.load(jid))[0]['state'], 'inactive')
        followups.set_followup(jid, '2028-01-01', ident='f1')
        self.assertEqual(followups.rows(jobs.load(jid))[0]['state'], 'active')

    def test_approval_and_snapshot_are_unchanged(self):
        jid = self.seed()
        package.propose_resume(jid, fixture('proposal_good.json'))
        package.accept_resume(jid)
        package.approve(jid)
        track.set_status(jid, 'applied')
        root = store.job_dir(jid)
        before = {str(p): p.read_bytes() for p in (root / 'snapshots').rglob('*') if p.is_file()}
        approval = (root / 'package.json').read_bytes()
        followups.set_followup(jid, '2028-01-01')
        followups.finish(jid, 'f1', 'cancelled')
        self.assertEqual((root / 'package.json').read_bytes(), approval)
        self.assertEqual(before, {str(p): p.read_bytes() for p in (root / 'snapshots').rglob('*') if p.is_file()})

    def test_invalid_stored_followups_are_reported(self):
        jid = self.seed()
        job = jobs.load(jid)
        for bad in (None, {}, [{}], [{'id': []}], [{'id': 'f1', 'state': []}]):
            job['tracking']['followups'] = bad
            store.write_json(store.job_dir(jid) / 'job.json', job)
            self.assertTrue(pipeline.report()['errors'])

    def test_cli_lock_refuses_other_process_and_preserves_unexplained_lock(self):
        jid = self.seed()
        script = str(ROOT / 'skills/resuskill/scripts/resuskill.py')
        with store.command_lock():
            child = subprocess.run([sys.executable, script, 'followup', 'set', jid, '--date', '2028-01-01'],
                                   capture_output=True, text=True, env=os.environ.copy())
            self.assertEqual(child.returncode, 1)
            self.assertIn('data lock', child.stderr)
        self.assertFalse((Path(self._tmp) / '.command-lock').exists())
        lock = Path(self._tmp) / '.command-lock'
        lock.mkdir()
        with self.assertRaises(ResuError):
            with store.command_lock():
                pass
        self.assertTrue(lock.exists())

    def test_failed_write_keeps_original_and_lock_is_released(self):
        jid = self.seed()
        path = store.job_dir(jid) / 'job.json'
        before = path.read_bytes()
        with patch.object(store.os, 'replace', side_effect=OSError('disk failure')):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(['followup', 'set', jid, '--date', '2028-01-01']), 1)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((Path(self._tmp) / '.command-lock').exists())
