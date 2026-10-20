"""A bounded, repeatable crash test using fictional stored records."""
import copy
import io
from contextlib import redirect_stdout, redirect_stderr

from helpers import IsolatedHome, fixture
from resuskill_core import package, store
from resuskill_core.cli import main


class StoredMutationTests(IsolatedHome):
    def test_wrong_types_do_not_crash_read_or_review_commands(self):
        job = self.seed()
        package.propose_resume(job, fixture('proposal_good.json'))
        package.accept_resume(job)
        paths = {'profile.json': store.profile_path(),
                 'job.json': store.job_dir(job) / 'job.json',
                 'package.json': store.job_dir(job) / 'package.json'}
        originals = {key: store.read_json(path) for key, path in paths.items()}
        fields = {'profile.json': ['contact', 'skills', '_meta', 'projects'],
                  'job.json': ['evidence', 'overrides', 'questions', 'tracking'],
                  'package.json': ['resume', 'answers', 'answer_proposals', 'approval']}
        values = (None, False, 0, {}, [], ['broken'], 'broken')
        commands = (['ats', job, '--proposal'], ['render', job, '--proposal'],
                    ['checklist', job], ['package', 'check', job])
        for filename, keys in fields.items():
            for key in keys:
                for value in values:
                    record = copy.deepcopy(originals[filename])
                    record[key] = value
                    store.write_json(paths[filename], record)
                    before = {name: path.read_bytes() for name, path in paths.items()}
                    for command in commands:
                        with self.subTest(file=filename, field=key, value=value, command=command), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                            self.assertIn(main(command), (0, 1))
                            self.assertEqual({name: path.read_bytes() for name, path in paths.items()}, before)
                    store.write_json(paths[filename], originals[filename])
