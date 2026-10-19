import json
import os
from pathlib import Path
from unittest import mock

from helpers import IsolatedHome, fixture
from resuskill_core import doctor, profile, render
from resuskill_core.util import ResuError


class DoctorTests(IsolatedHome):
    def test_fresh_setup_does_not_create_storage(self):
        root = Path(self._tmp) / "new" / "data"
        with mock.patch.dict(os.environ, {"RESUSKILL_HOME": str(root)}), mock.patch.object(render, "find_browser", return_value=None):
            result = doctor.check()
        self.assertTrue(result["ready"])
        self.assertFalse(root.exists())
        self.assertEqual(next(c for c in result["checks"] if c["name"] == "profile")["status"], "warning")

    def test_corrupt_profile_is_reported_without_disclosing_or_changing_it(self):
        path = Path(self._tmp) / "profile.json"
        content = '{"secret": "private-email",'
        path.write_text(content)
        result = doctor.check()
        self.assertFalse(result["ready"])
        self.assertNotIn("private-email", json.dumps(result))
        self.assertEqual(path.read_text(), content)

    def test_valid_profile_is_unchanged(self):
        profile.save(fixture("profile.json"))
        path = Path(self._tmp) / "profile.json"
        before = path.read_bytes()
        self.assertTrue(doctor.check()["ready"])
        self.assertEqual(path.read_bytes(), before)

    def test_explicit_pdf_check_reports_failure_and_cleans_up(self):
        with mock.patch.object(render, "print_pdf", side_effect=ResuError("Browser launch failed")) as printer:
            result = doctor.check(pdf_smoke=True)
        self.assertFalse(result["ready"])
        self.assertEqual(printer.call_count, 1)
        self.assertFalse(printer.call_args.args[0].exists())

    def test_storage_path_cannot_be_a_file(self):
        path = Path(self._tmp) / "file"
        path.write_text("unchanged")
        with mock.patch.dict(os.environ, {"RESUSKILL_HOME": str(path)}):
            self.assertFalse(doctor.check()["ready"])
        self.assertEqual(path.read_text(), "unchanged")
