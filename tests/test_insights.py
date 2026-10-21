import contextlib
import io
import json
from pathlib import Path

from helpers import IsolatedHome, fixture
from resuskill_core import cli, insights, jobs, profile, store


class InsightsTests(IsolatedHome):
    def test_unknown_is_not_a_confirmed_skill_gap(self):
        self.seed()
        result = insights.report()
        rust = next(g for g in result['gaps'] if g['requirement'] == 'Rust')
        alternatives = next(g for g in result['gaps'] if g['requirement'] == 'Java or Kafka')
        self.assertEqual(rust['kind'], 'confirmed_skill_gap')
        self.assertEqual(alternatives['kind'], 'missing_evidence')
        self.assertEqual(alternatives['criterion']['match'], 'any')
        self.assertEqual(len(alternatives['criterion']['skills']), 2)

    def test_recurrence_counts_distinct_jobs_and_keeps_any_all_separate(self):
        first = self.seed()
        second = jobs.add('Second', 'Engineer', fixture('job.txt'))['id']
        reqs = fixture('requirements.json')
        duplicate = dict(reqs[-2], id='r8')
        reqs.append(duplicate)
        jobs.set_requirements(first, reqs)
        reqs = fixture('requirements.json')
        reqs[4]['criterion']['match'] = 'all'
        jobs.set_requirements(second, reqs)
        result = insights.report()
        rust = next(g for g in result['gaps'] if g['requirement'] == 'Rust')
        self.assertEqual(rust['job_count'], 2)
        self.assertEqual(len(rust['occurrences']), 3)
        alternatives = [g for g in result['gaps'] if g['requirement'] == 'Java or Kafka']
        self.assertEqual(len(alternatives), 2)

    def test_outcomes_are_current_states_without_assumed_funnel(self):
        jid = self.seed()
        job = jobs.load(jid)
        job['tracking']['status'] = 'interview'
        job['tracking']['history'] = None  # No usable submission history is needed or invented.
        jobs.save(job)
        result = insights.report()
        self.assertEqual(result['outcomes']['interview'], 1)
        self.assertEqual(result['outcomes']['applied'], 0)
        self.assertIn('not a conversion funnel', result['warnings'][0])

    def test_current_profile_recalculates_gaps_without_writing(self):
        self.seed()
        data = profile.load()
        data['skills_absent'] = []
        profile.save(data)
        before = {str(p): p.read_bytes() for p in Path(self._tmp).rglob('*.json')}
        result = insights.report()
        self.assertEqual(next(g for g in result['gaps'] if g['requirement'] == 'Rust')['kind'], 'missing_evidence')
        self.assertEqual(before, {str(p): p.read_bytes() for p in Path(self._tmp).rglob('*.json')})

    def test_missing_profile_and_unreviewed_requirements_are_explicit(self):
        jobs.add('Company', 'Role', 'Description')
        result = insights.report()
        self.assertEqual(result['recorded_jobs'], 1)
        self.assertEqual(result['jobs_evaluated_for_gaps'], 0)
        self.assertIsNone(result['profile_revision'])
        profile.save(fixture('profile.json'))
        self.assertEqual(len(insights.report()['unreviewed_jobs']), 1)

    def test_corrupt_job_and_invalid_status_do_not_hide_readable_jobs(self):
        self.seed()
        bad = jobs.add('Bad', 'Role', 'Description')
        bad['tracking']['status'] = 'made-up'
        jobs.save(bad)
        damaged = store.jobs_dir() / 'damaged'
        damaged.mkdir()
        (damaged / 'job.json').write_text('{')
        result = insights.report()
        self.assertEqual(result['recorded_jobs'], 1)
        self.assertEqual(len(result['errors']), 2)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(['insights', '--json']), 1)
        self.assertEqual(json.loads(output.getvalue())['recorded_jobs'], 1)

    def test_override_is_not_presented_as_confirmed_missing_skill(self):
        from resuskill_core import checklist
        jid = self.seed()
        checklist.override(jid, 'r5', 'unmet', 'User review')
        group = next(g for g in insights.report()['gaps'] if g['requirement'] == 'Java or Kafka')
        self.assertEqual(group['kind'], 'user_assessed_gap')

    def test_stale_evidence_is_actionable_even_if_computed_met(self):
        from resuskill_core import checklist
        jid = self.seed()
        checklist.link(jid, 'r1', ['exp-1-b1'])
        data = profile.load()
        data['experience'][0]['bullets'][0]['text'] += ' Updated.'
        profile.save(data)
        group = next(g for g in insights.report()['gaps'] if g['requirement'] == 'Experience with Python and SQL')
        self.assertEqual(group['kind'], 'evidence_needs_review')
