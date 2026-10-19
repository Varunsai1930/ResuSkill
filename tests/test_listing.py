from datetime import datetime, timezone
from pathlib import Path

from helpers import IsolatedHome, fixture
from resuskill_core import jobs, listing, package, profile, render, store, track
from resuskill_core.util import ResuError


class ListingTests(IsolatedHome):
    NOW = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)

    def observation(self, **changes):
        return {"status": "open", "verified_at": "2026-10-18T12:00:00Z",
                "source_url": "https://example.test/jobs/1", "status_excerpt": "Apply now",
                "deadline": "2026-10-24", **changes}

    def assess(self, **changes):
        return listing.assess({'listing': self.observation(**changes)}, now=self.NOW)

    def test_saved_job_is_not_an_open_observation(self):
        job = jobs.load(self.seed())
        self.assertEqual(listing.assess(job)['state'], 'unverified')
        self.assertEqual(track.rows()[0]['listing']['state'], 'unverified')

    def test_status_age_deadline_and_future_observations(self):
        for fields, state in [({}, 'observed_open'), ({'status': 'closed'}, 'closed'),
                              ({'verified_at': '2026-10-01T12:00:00Z'}, 'stale'),
                              ({'deadline': '2026-10-18'}, 'expired'),
                              ({'verified_at': '2027-10-18T12:00:00Z'}, 'unverified')]:
            with self.subTest(fields=fields):
                self.assertEqual(self.assess(**fields)['state'], state)

    def test_date_only_deadline_includes_whole_day_and_precise_deadline_uses_offset(self):
        self.assertEqual(self.assess(deadline='2026-10-19')['state'], 'observed_open')
        self.assertEqual(self.assess(deadline='2026-10-19T17:00:00+05:30')['state'], 'expired')
        self.assertEqual(self.assess(deadline='2026-10-19T08:00:00-05:00')['state'], 'observed_open')

    def test_invalid_metadata_is_rejected_without_writing(self):
        job_id = self.seed()
        path = store.job_dir(job_id) / 'job.json'
        before = path.read_bytes()
        invalid = [self.observation(verified_at='2026-10-18'), self.observation(source_url='javascript:alert(1)'),
                   self.observation(status_excerpt=''), self.observation(deadline='2026-02-30'),
                   self.observation(eligibility='conditional'), self.observation(verified_at=True),
                   self.observation(program_start='2026-10-24', program_end='2026-10-01'),
                   {'status': 'open'}, {'typo': 'open'}]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ResuError):
                jobs.observe(job_id, data)
            self.assertEqual(path.read_bytes(), before)

    def test_observation_invalidates_approval_and_identical_update_is_noop(self):
        job = self.seed()
        package.propose_resume(job, fixture('proposal_good.json'))
        package.accept_resume(job)
        package.approve(job)
        result = jobs.observe(job, self.observation())
        self.assertEqual(package.review_state(result, package.load(job), profile.load()), 'stale')
        self.assertEqual(result, jobs.observe(job, self.observation()))

    def test_conditional_intake_and_escaping_are_visible_in_review(self):
        job = self.seed()
        jobs.observe(job, self.observation(eligibility='conditional', eligibility_note='Relocation required <script>',
                                          intake_note='Summer year unknown'))
        warnings = package.check(job)[1]
        self.assertTrue(any('Relocation required' in w for w in warnings))
        self.assertTrue(any('Summer year unknown' in w for w in warnings))
        body = Path(render.render(job)['review']).read_text()
        self.assertIn('&lt;script&gt;', body)
        self.assertNotIn('<script>', body)

    def test_closed_jobs_remain_available_for_historical_tracking(self):
        job = self.seed()
        jobs.observe(job, self.observation(status='closed'))
        self.assertEqual(track.set_status(job, 'rejected')['tracking']['status'], 'rejected')
        self.assertEqual(track.rows()[0]['listing']['state'], 'closed')
