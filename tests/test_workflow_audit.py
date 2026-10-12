"""Regression checks for stored question mappings and damaged package state."""

from helpers import IsolatedHome, fixture
from resuskill_core import jobs, package, profile, questions, store, track
from resuskill_core.util import ResuError


class WorkflowAuditTests(IsolatedHome):
    def setUp(self):
        super().setUp()
        self.job_id = self.seed()
        package.propose_resume(self.job_id, fixture("proposal_good.json"))
        package.accept_resume(self.job_id)

    def test_legacy_authorization_mapping_needs_user_confirmation(self):
        question = package.add_question(
            self.job_id, "Are you authorized to work in the United States?",
            True, None, "chars", None,
        )
        job = jobs.load(self.job_id)
        job["questions"][0]["category"] = questions.FACTUAL
        jobs.save(job)
        resolved = package.resolved(job, profile.load(), package.load(self.job_id))
        self.assertFalse(resolved["answers"][0]["resolved"])
        with self.assertRaises(ResuError):
            package.approve(self.job_id)
        package.set_category(self.job_id, question["id"], questions.SENSITIVE_FACTUAL)
        package.confirm_answer(self.job_id, question["id"])
        self.assertEqual(package.check(self.job_id)[0], [])

    def test_factual_field_can_still_require_confirmation(self):
        question = package.add_question(
            self.job_id, "Full name", True, None, "chars", questions.SENSITIVE_FACTUAL,
        )
        package.confirm_answer(self.job_id, question["id"])
        self.assertEqual(package.check(self.job_id)[0], [])

    def test_damaged_answer_container_keeps_tracker_usable(self):
        pkg = package.load(self.job_id)
        pkg["answers"] = None
        store.write_json(store.job_dir(self.job_id) / "package.json", pkg)
        with self.assertRaises(ResuError):
            package.load(self.job_id)
        rows = track.rows()
        self.assertEqual(rows[0]["review"], "unreadable")

    def test_damaged_approval_keeps_tracker_usable(self):
        pkg = package.load(self.job_id)
        pkg["approval"] = {"hash": "missing required revisions"}
        store.write_json(store.job_dir(self.job_id) / "package.json", pkg)
        rows = track.rows()
        self.assertEqual(rows[0]["review"], "unreadable")

    def test_damaged_answer_reports_recovery_error(self):
        question = package.add_question(
            self.job_id, "Why do you want to work here?", True, None, "chars", None,
        )
        pkg = package.load(self.job_id)
        pkg["answers"][question["id"]] = {"text": "I enjoy backend work", "source": "unknown"}
        store.write_json(store.job_dir(self.job_id) / "package.json", pkg)
        with self.assertRaises(ResuError):
            package.check(self.job_id)
