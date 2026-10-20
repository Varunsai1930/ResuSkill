import copy
import io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from helpers import IsolatedHome, fixture
from resuskill_core import package, store
from resuskill_core.cli import main


class ProposalRecoveryTests(IsolatedHome):
    def test_malformed_records_are_rejected_across_read_and_export_commands(self):
        job = self.seed()
        package.propose_resume(job, fixture('proposal_good.json'))
        good = package.load_proposal(job)
        missing = copy.deepcopy(good)
        missing['proposal']['projects'][0].pop('entry')
        bad_metadata = copy.deepcopy(good)
        bad_metadata['created_at'] = []
        path = store.job_dir(job) / 'proposal.json'
        for record in (['broken'], {'proposal': 'broken'}, missing, bad_metadata):
            store.write_json(path, record)
            before = path.read_bytes()
            for command in (['resume', 'show', job, '--proposal'],
                            ['render', job, '--proposal'],
                            ['batch-export', job, '--output', str(Path(self._tmp) / 'pack')],
                            ['ats', job, '--proposal']):
                with self.subTest(record=record, command=command), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    code = main(command)
                    self.assertEqual(code, 1)
                self.assertEqual(path.read_bytes(), before)
                self.assertFalse((Path(self._tmp) / 'pack').exists())
