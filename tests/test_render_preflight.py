from pathlib import Path
from unittest.mock import patch
from helpers import IsolatedHome, fixture
from resuskill_core import package, profile, render, store
from resuskill_core.util import ResuError


class RenderPreflightTests(IsolatedHome):
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
