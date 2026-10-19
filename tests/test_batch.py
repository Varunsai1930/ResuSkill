import json
import zipfile
from pathlib import Path
from unittest.mock import patch
from helpers import IsolatedHome, fixture
from resuskill_core import batch, jobs, package, store
from resuskill_core.util import ResuError


class BatchTests(IsolatedHome):
    def ready(self):
        job = self.seed()
        package.propose_resume(job, fixture('proposal_good.json'))
        return job

    def test_pack_keeps_pending_state_and_omits_old_files(self):
        job = self.ready()
        before = package.load(job)
        old = store.job_dir(job) / 'out'
        old.mkdir()
        (old / 'stale.pdf').write_bytes(b'old')
        result = batch.export([job], Path(self._tmp) / 'pack')
        self.assertEqual(package.load(job), before)
        self.assertEqual(result['errors'], [])
        with zipfile.ZipFile(Path(result['output']) / 'resumes.zip') as z:
            self.assertEqual(len(z.namelist()), 4)
            self.assertFalse(any(p.endswith('.pdf') for p in z.namelist()))
            self.assertIn('review required', z.read('index.html').decode())

    def test_preflight_failure_leaves_no_partial_pack(self):
        job = self.ready()
        other = jobs.add('Other', 'Engineer', 'Python')['id']
        dest = Path(self._tmp) / 'pack'
        with self.assertRaises(ResuError):
            batch.export([job, other], dest)
        self.assertFalse(dest.exists())
        with self.assertRaises(ResuError):
            batch.export([job, job], dest)
        self.assertFalse(dest.exists())

    def test_pdf_failure_retains_html_and_reports_failure(self):
        job = self.ready()
        with patch('resuskill_core.render.print_pdf', side_effect=ResuError('PDF unavailable')):
            result = batch.export([job], Path(self._tmp) / 'pack', want_pdf=True)
        self.assertEqual(len(result['errors']), 1)
        with zipfile.ZipFile(Path(result['output']) / 'resumes.zip') as z:
            self.assertFalse(any(p.endswith('.pdf') for p in z.namelist()))
            self.assertEqual(json.loads(z.read('report.json'))['errors'], result['errors'])
        self.assertIsNone(package.load(job)['approval'])

    def test_existing_output_and_invalid_style_are_not_modified(self):
        job = self.ready()
        dest = Path(self._tmp) / 'pack'
        with self.assertRaises(ResuError):
            batch.export([job], dest, style={'font_size_pt': 1})
        self.assertFalse(dest.exists())
        dest.mkdir()
        (dest / 'keep').write_text('keep')
        with self.assertRaises(ResuError):
            batch.export([job], dest)
        self.assertEqual((dest / 'keep').read_text(), 'keep')

    def test_multiple_jobs_and_accepted_selection(self):
        job = self.ready()
        other = jobs.add('Second & Co', 'Backend Engineer', fixture('job.txt'))['id']
        jobs.set_requirements(other, fixture('requirements.json'))
        package.propose_resume(other, fixture('proposal_good.json'))
        for selected in [job, other]:
            package.accept_resume(selected)
        before = [package.load(selected) for selected in [job, other]]
        result = batch.export([job, other], Path(self._tmp) / 'pack', accepted=True)
        self.assertEqual(len(result['jobs']), 2)
        self.assertEqual([package.load(selected) for selected in [job, other]], before)
        html = (Path(result['output']) / 'index.html').read_text()
        self.assertIn('Second &amp; Co', html)

    def test_cli_pdf_failure_returns_nonzero(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from resuskill_core.cli import main
        job = self.ready()
        output = StringIO()
        with patch('resuskill_core.render.print_pdf', side_effect=ResuError('No browser')), redirect_stdout(output):
            code = main(['batch-export', job, '--output', str(Path(self._tmp) / 'pack'), '--pdf', '--json'])
        self.assertEqual(code, 1)
        self.assertEqual(len(json.loads(output.getvalue())['errors']), 1)
