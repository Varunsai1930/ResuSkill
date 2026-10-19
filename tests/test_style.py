import copy
from pathlib import Path
from unittest import mock

from helpers import IsolatedHome, fixture
from resuskill_core import package, profile, render, store, style, track
from resuskill_core.util import ResuError


class StyleTests(IsolatedHome):
    def test_rejects_injection_unknown_options_and_hidden_sections(self):
        for value in ({"accent": "red;display:none"}, {"font": "url(https://example.test)"},
                      {"font_size_pt": True}, {"font_size_pt": 0}, {"css": "body{}"},
                      {"section_order": ["summary"]}, {"margin_mm": float('nan')}):
            with self.subTest(value=value), self.assertRaises(ResuError):
                style.normalize(value)

    def test_reordering_keeps_all_content_and_escapes_link_labels(self):
        job = self.seed()
        package.propose_resume(job, fixture("proposal_good.json"))
        prof = profile.load()
        prof["contact"]["links"] = {"<script>bad</script>": "https://example.test"}
        settings = {"section_order": list(reversed(style.DEFAULT["section_order"])), "link_labels": True,
                    "degree_first": True, "uppercase_name": True}
        proposal = package.load_proposal(job)["proposal"]
        html = render.resume_html(prof, proposal, "Example", settings)
        self.assertLess(html.index('<h2>Skills'), html.index('<h2>Summary'))
        self.assertIn('text-transform: uppercase', html)
        self.assertIn('&lt;script&gt;bad&lt;/script&gt;', html)
        self.assertNotIn('<script>', html)
        for entry in proposal['experience']:
            for bullet in entry['bullets']:
                self.assertIn(render._e(bullet['text']), html)

    def test_saved_style_is_reused_without_changing_proposal_or_approval(self):
        job = self.seed()
        package.propose_resume(job, fixture("proposal_good.json"))
        before = package.load_proposal(job)
        first = render.render(job, use_proposal=True, style={"name_size_pt": 25})
        original = Path(first['resume']).read_text()
        render.render(job, use_proposal=True)
        self.assertEqual(original, Path(first['resume']).read_text())
        self.assertEqual(before, package.load_proposal(job))
        self.assertIsNone(package.load(job)['approval'])
        render.render(job, use_proposal=True, style={})
        self.assertNotEqual(original, Path(first['resume']).read_text())

    def test_invalid_style_does_not_replace_existing_outputs(self):
        job = self.seed()
        package.propose_resume(job, fixture("proposal_good.json"))
        path = Path(render.render(job, use_proposal=True)['resume'])
        before = path.read_bytes()
        with self.assertRaises(ResuError):
            render.render(job, use_proposal=True, style={"font_size_pt": -1})
        self.assertEqual(path.read_bytes(), before)

    def test_snapshot_does_not_pair_new_style_with_old_pdf(self):
        job = self.seed()
        package.propose_resume(job, fixture("proposal_good.json"))
        package.accept_resume(job)
        def pdf(html, output):
            output.write_bytes(b'%PDF-1.4\n%%EOF\n')
            return output
        with mock.patch.object(render, 'print_pdf', side_effect=pdf):
            render.render(job, want_pdf=True, style={'name_size_pt': 25})
        render.render(job, style={'name_size_pt': 22})
        package.approve(job)
        snap = track.snapshot(job)
        result = store.read_json(store.job_dir(job) / 'snapshots' / snap / 'package.json')
        self.assertIsNone(result['pdf'])
        self.assertEqual(result['render_style']['name_size_pt'], 22)
