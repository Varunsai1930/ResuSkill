from pathlib import Path
from unittest.mock import patch
from helpers import IsolatedHome, fixture
from resuskill_core import package, profile, render, store
from resuskill_core.util import ResuError


class RenderPreflightTests(IsolatedHome):
    def test_partial_staging_write_keeps_all_previous_exports(self):
        job = self.seed()
        package.propose_resume(job, fixture('proposal_good.json'))
        package.accept_resume(job)
        render.render(job, style={'name_size_pt': 20})
        folder = render.out_dir(job)
        before = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
        original = Path.write_text
        def interrupted(path, text, *args, **kwargs):
            if path.name == 'resume.html' and path.parent.name.startswith('.render-'):
                with path.open('w', encoding='utf-8') as stream:
                    stream.write(text[:40])
                raise OSError('injected partial write')
            return original(path, text, *args, **kwargs)
        with patch.object(Path, 'write_text', interrupted), self.assertRaises(OSError):
            render.render(job, style={'name_size_pt': 25})
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()})
        self.assertEqual(list(folder.glob('.render-*')), [])

    def test_failed_publication_restores_existing_files_and_removes_new_ones(self):
        job = self.seed()
        package.propose_resume(job, fixture('proposal_good.json'))
        render.render(job, use_proposal=True)
        folder = render.out_dir(job)
        before = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
        real_replace = render.os.replace
        for failure in (OSError('injected replacement failure'), KeyboardInterrupt()):
            def interrupted(source, target):
                if Path(source).name == 'style.json' and Path(source).parent.name.startswith('.render-'):
                    raise failure
                return real_replace(source, target)
            with self.subTest(failure=type(failure).__name__), patch.object(render.os, 'replace', interrupted), self.assertRaises(type(failure)):
                render.render(job, use_proposal=True, style={'name_size_pt': 25})
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()})
            self.assertEqual(list(folder.glob('.render-*')), [])

    def test_failed_rollback_retains_recovery_copies(self):
        job = self.seed()
        package.propose_resume(job, fixture('proposal_good.json'))
        render.render(job, use_proposal=True)
        folder = render.out_dir(job)
        before = (folder / 'review.html').read_bytes()
        real_replace = render.os.replace
        def interrupted(source, target):
            if Path(source).name == 'preview.html' or Path(source).parent.name == 'previous':
                raise OSError('injected persistent failure')
            return real_replace(source, target)
        with patch.object(render.os, 'replace', interrupted), self.assertRaises(ResuError) as error:
            render.render(job, use_proposal=True)
        self.assertIn('Previous files are retained', str(error.exception))
        recovery = list(folder.glob('.render-*/previous/review.html'))
        self.assertEqual(len(recovery), 1)
        self.assertEqual(recovery[0].read_bytes(), before)

    def _assert_stale_rejected(self, accepted):
        job = self.seed()
        package.propose_resume(job, fixture('proposal_good.json'))
        if accepted:
            package.accept_resume(job)
        render.render(job, use_proposal=not accepted)
        folder = store.job_dir(job) / 'out'
        before = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
        prof = profile.load()
        prof['experience'][0]['bullets'][0]['text'] = 'Built a Flask REST API in Python that served reporting data to 500 internal users'
        profile.save(prof)
        with patch.object(render, 'print_pdf') as pdf, self.assertRaises(ResuError):
            render.render(job, want_pdf=True, use_proposal=not accepted, style={'name_size_pt': 25})
        pdf.assert_not_called()
        after = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
        self.assertEqual(before, after)

    def test_changed_source_rejects_pending_export(self):
        self._assert_stale_rejected(False)

    def test_changed_source_rejects_accepted_export(self):
        self._assert_stale_rejected(True)

    def test_valid_pending_draft_can_be_reviewed_without_accepting_it(self):
        job = self.seed()
        package.propose_resume(job, fixture('proposal_good.json'))
        result = render.render(job, use_proposal=True)
        self.assertTrue(Path(result['resume']).is_file())
        self.assertIsNone(package.load(job)['resume'])
