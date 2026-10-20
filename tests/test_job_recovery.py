import copy
import io
from contextlib import redirect_stdout, redirect_stderr
from helpers import IsolatedHome, fixture
from resuskill_core import checklist, jobs, package, store
from resuskill_core.cli import main


class JobRecoveryTests(IsolatedHome):
    def test_malformed_evidence_overrides_and_questions_fail_before_review(self):
        job = self.seed()
        package.propose_resume(job, fixture('proposal_good.json'))
        original = jobs.load(job)
        cases = []
        for field in ('evidence', 'overrides', 'questions'):
            for value in (None, False, 0, 'broken', ['broken']):
                bad = copy.deepcopy(original)
                bad[field] = value
                cases.append(bad)
        for field, value in [('evidence', {'r1': {'sources': [None]}}),
                             ('evidence', {'r1': {'sources': ['exp-1-b1'], 'source_hashes': []}}),
                             ('overrides', {'r1': {'profile_revision': 1}}),
                             ('questions', [{'id': 'q1', 'text': 'Question'}])]:
            bad = copy.deepcopy(original)
            bad[field] = value
            cases.append(bad)
        path = store.job_dir(job) / 'job.json'
        for bad in cases:
            store.write_json(path, bad)
            before = path.read_bytes()
            for command in (['checklist', job], ['render', job, '--proposal'], ['package', 'check', job]):
                with self.subTest(command=command, job=bad), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(main(command), 1)
                self.assertEqual(path.read_bytes(), before)

    def test_legacy_evidence_without_hashes_remains_readable(self):
        job = self.seed()
        checklist.link(job, 'r4', ['exp-1-b1'])
        record = jobs.load(job)
        record['evidence']['r4'].pop('source_hashes')
        store.write_json(store.job_dir(job) / 'job.json', record)
        self.assertEqual(jobs.load(job), record)
