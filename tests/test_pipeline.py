import contextlib
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from helpers import IsolatedHome, fixture
from resuskill_core import cli, jobs, package, pipeline, profile, store
from resuskill_core.util import ResuError, now_iso


class PipelineTests(IsolatedHome):
    def fresh(self, jid):
        jobs.observe(jid, {'status': 'open', 'verified_at': now_iso(),
                          'source_url': 'https://example.com/jobs', 'status_excerpt': 'Apply now',
                          'deadline': (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat(),
                          'eligibility': 'preference_match'})

    def ready(self):
        jid = self.seed(with_requirements=False)
        jobs.set_requirements(jid, [])
        self.fresh(jid)
        package.propose_resume(jid, fixture('proposal_good.json'))
        package.accept_resume(jid)
        return jid

    def test_missing_profile_and_unverified_listing_are_clear(self):
        jid = jobs.add('Company', 'Role', 'Description')['id']
        row = pipeline.report()['jobs'][0]
        self.assertEqual(row['next_action']['code'], 'set_up_profile')
        self.assertIsNone(row['checklist'])
        profile.save(fixture('profile.json'))
        self.assertEqual(pipeline.report()['jobs'][0]['next_action']['code'], 'recheck_listing')
        self.fresh(jid)
        self.assertEqual(pipeline.report()['jobs'][0]['next_action']['code'], 'resolve_blockers')

    def test_approved_and_stale_packages_have_distinct_actions(self):
        jid = self.ready()
        self.assertEqual(pipeline.report()['jobs'][0]['next_action']['code'], 'review_package')
        package.approve(jid)
        row = pipeline.report()['jobs'][0]
        self.assertEqual(row['review'], 'approved')
        self.assertEqual(row['next_action']['code'], 'submit_manually')
        data = profile.load()
        data['contact']['phone'] = '555-9999'
        profile.save(data)
        row = pipeline.report()['jobs'][0]
        self.assertEqual(row['review'], 'stale')
        self.assertEqual(row['next_action']['code'], 'review_stale')

    def test_approved_package_with_pending_draft_requires_review(self):
        jid = self.ready()
        package.approve(jid)
        draft = fixture('proposal_good.json')
        draft['experience'][0]['bullets'][0]['text'] = 'Built a Flask API for 1,200 users'
        package.propose_resume(jid, draft)
        row = pipeline.report()['jobs'][0]
        self.assertTrue(row['pending_resume'])
        self.assertEqual(row['review'], 'approved')
        self.assertEqual(row['next_action']['code'], 'review_drafts')

    def test_sensitive_question_blocker_and_fit_evidence_visible(self):
        jid = self.seed()
        self.fresh(jid)
        package.add_question(jid, 'What are your salary expectations?', True, None, 'chars', None)
        row = pipeline.report()['jobs'][0]
        self.assertTrue(any('sensitive' in b for b in row['blockers']))
        self.assertTrue(any('Rust' in w and 'unmet' in w for w in row['warnings']))
        self.assertEqual(row['next_action']['code'], 'resolve_blockers')

    def test_submitted_and_closed_states_never_suggest_resubmitting(self):
        jid = self.seed()
        for status, code in [('applied', 'record_progress'), ('interview', 'record_progress'),
                             ('offer', 'review_offer'), ('rejected', 'closed'), ('withdrawn', 'closed')]:
            job = jobs.load(jid)
            job['tracking']['status'] = status
            job['tracking']['history'] = None
            jobs.save(job)
            self.assertEqual(pipeline.report()['jobs'][0]['next_action']['code'], code)

    def test_expired_and_future_observations_need_rechecking(self):
        jid = self.ready()
        job = jobs.load(jid)
        job['listing']['deadline'] = '2000-01-01'
        jobs.save(job)
        row = pipeline.report()['jobs'][0]
        self.assertEqual(row['listing']['state'], 'expired')
        self.assertEqual(row['next_action']['code'], 'recheck_listing')
        self.fresh(jid)
        job = jobs.load(jid)
        job['listing']['verified_at'] = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        jobs.save(job)
        self.assertEqual(pipeline.report()['jobs'][0]['listing']['state'], 'unverified')

    def test_damaged_records_are_visible_and_sorted_first(self):
        good = self.seed()
        bad = jobs.add('Bad', 'Role', 'Description')['id']
        store.write_json(store.job_dir(bad) / 'package.json', {'answers': []})
        folder = store.jobs_dir() / 'broken'
        folder.mkdir()
        (folder / 'job.json').write_text('{')
        result = pipeline.report()
        self.assertEqual(len(result['jobs']), 3)
        self.assertEqual(len(result['errors']), 2)
        self.assertEqual(result['jobs'][0]['next_action']['code'], 'repair_record')
        self.assertTrue(any(row['id'] == good for row in result['jobs']))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(['pipeline', '--json']), 1)
        self.assertEqual(len(json.loads(output.getvalue())['errors']), 2)

    def test_report_and_export_preserve_candidate_records_and_escape_html(self):
        jid = self.ready()
        job = jobs.load(jid)
        job['company'] = '<script>alert("x")</script>'
        jobs.save(job)
        before = {str(p): p.read_bytes() for p in Path(self._tmp).rglob('*.json')}
        result = pipeline.report()
        self.assertEqual(before, {str(p): p.read_bytes() for p in Path(self._tmp).rglob('*.json')})
        target = Path(self._tmp) / 'reports'
        files = pipeline.export(result, str(target))
        html = Path(files['html']).read_text()
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('No messages are sent', html)
        for name, content in before.items():
            self.assertEqual(Path(name).read_bytes(), content)
        with self.assertRaises(ResuError):
            pipeline.export(result, str(target))
        self.assertEqual(Path(files['html']).read_text(), html)

    def test_empty_pipeline_cli_export(self):
        target = Path(self._tmp) / 'new-report'
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(['pipeline', '--output', str(target), '--json']), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result['jobs'], [])
        self.assertTrue(Path(result['files']['html']).exists())
        self.assertIn('No saved jobs yet', Path(result['files']['html']).read_text())
