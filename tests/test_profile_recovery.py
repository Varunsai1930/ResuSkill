import copy
import io
from contextlib import redirect_stdout, redirect_stderr
from helpers import IsolatedHome, fixture
from resuskill_core import package, profile, store
from resuskill_core.cli import main


class ProfileRecoveryTests(IsolatedHome):
    def test_corrupt_profiles_refuse_cleanly_without_repair_or_overwrite(self):
        job = self.seed()
        package.propose_resume(job, fixture('proposal_good.json'))
        original = profile.load()
        cases = []
        for key, value in [('skills', [None]), ('skills', ['Python']), ('contact', None),
                           ('projects', [{'name': 'Missing stored IDs'}])]:
            bad = copy.deepcopy(original)
            bad[key] = value
            cases.append(bad)
        for key, value in [('revision', 'broken'), ('revision', True), ('id_counters', None),
                           ('id_counters', {'proj': 'broken'})]:
            bad = copy.deepcopy(original)
            bad['_meta'][key] = value
            cases.append(bad)
        for bad in cases:
            store.write_json(store.profile_path(), bad)
            before = store.profile_path().read_bytes()
            for command in (['profile', 'show'], ['ats', job, '--proposal'], ['render', job, '--proposal']):
                with self.subTest(profile=bad, command=command), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(main(command), 1)
                self.assertEqual(store.profile_path().read_bytes(), before)

    def test_normal_reads_preserve_ids_metadata_and_bytes(self):
        self.seed()
        before = store.profile_path().read_bytes()
        first = profile.load()
        self.assertEqual(first, profile.load())
        self.assertEqual(store.profile_path().read_bytes(), before)
