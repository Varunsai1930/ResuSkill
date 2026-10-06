"""Shared test setup: isolated data directory and fixture loading."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "skills" / "resuskill" / "scripts"))

JOB_ID = "demo-corp-backend-engineering-intern"


def fixture(name: str):
    path = FIXTURES / name
    return path.read_text(encoding="utf-8") if path.suffix == ".txt" else json.loads(path.read_text(encoding="utf-8"))


class IsolatedHome(unittest.TestCase):
    """Each test gets its own RESUSKILL_HOME."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="resuskill-test-")
        self._old = os.environ.get("RESUSKILL_HOME")
        os.environ["RESUSKILL_HOME"] = self._tmp

    def tearDown(self):
        if self._old is None:
            os.environ.pop("RESUSKILL_HOME", None)
        else:
            os.environ["RESUSKILL_HOME"] = self._old
        shutil.rmtree(self._tmp, ignore_errors=True)

    def seed(self, with_requirements: bool = True) -> str:
        from resuskill_core import jobs, profile

        profile.save(fixture("profile.json"))
        job = jobs.add("Demo Corp", "Backend Engineering Intern", fixture("job.txt"), "Austin, TX")
        if with_requirements:
            jobs.set_requirements(job["id"], fixture("requirements.json"))
        return job["id"]
