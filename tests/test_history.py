from pathlib import Path
from helpers import IsolatedHome, fixture
from resuskill_core import history, jobs, package, profile, store, track
from resuskill_core.util import ResuError


class HistoryTests(IsolatedHome):
    def submitted(self):
        jid = self.seed()
        package.propose_resume(jid, fixture('proposal_good.json'))
        package.accept_resume(jid)
        package.approve(jid)
        track.set_status(jid, 'applied')
        return jid

    def test_frozen_fit_survives_profile_edit_and_deduplicates_stages(self):
        jid = self.submitted()
        track.set_status(jid, 'interview')
        track.set_status(jid, 'interview')
        first = history.report()
        data = profile.load()
        data['skills_absent'] = []
        profile.save(data)
        second = history.report()
        self.assertEqual(first['applications'], second['applications'])
        self.assertEqual(second['reached_stages']['interview'], 1)
        self.assertEqual(second['history_denominator'], 1)
        self.assertIsNone(second['reached_percentages'])

    def test_filters_and_missing_dates(self):
        jid = self.submitted()
        day = jobs.load(jid)['tracking']['applied_at'][:10]
        self.assertEqual(history.report(day, day)['cohort_count'], 1)
        self.assertEqual(history.report('2000-01-01', '2000-01-02')['cohort_count'], 0)
        job = jobs.load(jid)
        del job['tracking']['applied_at']
        jobs.save(job)
        self.assertEqual(history.report()['cohort_count'], 0)
        self.assertTrue(history.report()['excluded'])
        with self.assertRaises(ResuError):
            history.report('2028-01-01', '2027-01-01')

    def test_contradictions_and_missing_snapshot_do_not_use_current_profile(self):
        jid = self.submitted()
        job = jobs.load(jid)
        job['tracking']['history'].reverse()
        job['tracking']['snapshot'] = '../../profile'
        jobs.save(job)
        result = history.report()
        self.assertEqual(result['history_denominator'], 0)
        self.assertEqual(result['fit_denominator'], 0)
        self.assertEqual(len(result['errors']), 2)
        self.assertIsNone(result['applications'][0]['submission_checklist'])

    def test_ten_application_threshold_and_no_writes(self):
        for _ in range(10):
            self.submitted()
        before = {str(p): p.read_bytes() for p in Path(self._tmp).rglob('*.json')}
        result = history.report()
        self.assertEqual(result['reached_percentages']['applied'], 100)
        self.assertEqual(result['fit_denominator'], 10)
        self.assertEqual(before, {str(p): p.read_bytes() for p in Path(self._tmp).rglob('*.json')})

    def test_damaged_history_and_frozen_checklist_are_visible(self):
        jid = self.submitted()
        job = jobs.load(jid)
        job['tracking']['history'] = [None]
        jobs.save(job)
        path = store.job_dir(jid) / 'snapshots' / job['tracking']['snapshot'] / 'package.json'
        frozen = store.read_json(path)
        frozen['checklist'][0]['status'] = []
        store.write_json(path, frozen)
        result = history.report()
        self.assertEqual(len(result['errors']), 2)
        self.assertEqual(result['cohort_count'], 1)

    def test_invalid_snapshot_path_does_not_hide_cohort(self):
        jid = self.submitted()
        job = jobs.load(jid)
        job['tracking']['snapshot'] = 'bad\x00snapshot'
        jobs.save(job)
        result = history.report()
        self.assertEqual(result['cohort_count'], 1)
        self.assertEqual(result['history_denominator'], 1)
        self.assertEqual(result['fit_denominator'], 0)
        self.assertEqual(len(result['errors']), 1)
