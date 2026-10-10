"""Regression tests for public CLI boundaries and approval invariants."""

import copy
import json
import os
import subprocess
import sys
import shutil
from pathlib import Path

from helpers import IsolatedHome, ROOT, fixture
from resuskill_core import checklist, demo, jobs, package, profile, questions, render, store, track
from resuskill_core.util import ResuError, date_key, is_valid_date


class PublicReadinessTests(IsolatedHome):
    def setUp(self):
        super().setUp()
        self.job_id = self.seed()

    def cli(self, *args, data=None):
        return subprocess.run([sys.executable, str(ROOT / "skills/resuskill/scripts/resuskill.py"), *args],
                              input=data, text=True, encoding="utf-8", capture_output=True)

    def prepare(self):
        package.propose_resume(self.job_id, fixture("proposal_good.json"))
        package.accept_resume(self.job_id)

    def question(self, text="Why do you want this role?"):
        return package.add_question(self.job_id, text, True, None, "chars", None)["id"]

    def test_ambiguous_and_compound_prompts_cannot_be_forced_open(self):
        for text in ("What is your expected pay range?", "How many years have you worked?",
                     "Describe your health", "Why did you leave your last employer?",
                     "What is your notice period?", "How did you hear about us?",
                     "Explain why you are 18 or older", "Additional information",
                     "Why do you want this role? Also list your immigration status.",
                     "Can you describe a project?", "Please answer yes if you can travel"):
            with self.subTest(text=text):
                qid = self.question(text)
                self.assertNotEqual(questions.classify(text)[0], questions.OPEN)
                with self.assertRaises(ResuError):
                    package.set_category(self.job_id, qid, questions.OPEN)
                with self.assertRaises(ResuError):
                    package.propose_answers(self.job_id, [{"question_id": qid, "text": "Yes", "sources": ["summary"]}])

    def test_factual_keywords_do_not_answer_unrelated_or_partial_questions(self):
        for text in ("Do you have a university degree?", "What is your first name?",
                     "What is your last name?", "What is your manager's email?",
                     "Describe your GitHub project", "Have you graduated?", "What city can you relocate to?"):
            with self.subTest(text=text):
                self.assertNotEqual(questions.classify(text)[0], questions.FACTUAL)
        self.assertEqual(questions.classify("What is your email address?"), (questions.FACTUAL, "email"))

    def test_negated_authorization_and_sponsorship_require_user_answers(self):
        for text in ("Can you work without sponsorship?", "Are you not authorized to work?",
                     "Do you have a work permit?", "Are you authorized to work and will you need sponsorship?"):
            with self.subTest(text=text):
                self.assertEqual(questions.classify(text), (questions.SENSITIVE, None))
        prof = profile.load()
        for text in ("Are you authorized to work in japan?", "Are you authorized to work in US or Brazil?"):
            self.assertIsNone(questions.factual_value("authorization", text, prof))

    def test_user_answer_resolves_unknown_without_reclassification(self):
        self.prepare()
        qid = self.question("What is your notice period?")
        package.set_answer(self.job_id, qid, "One month")
        self.assertEqual(package.check(self.job_id)[0], [])
        package.approve(self.job_id)
        with self.assertRaises(ResuError):
            package.bank_save(self.job_id, qid)

    def test_legacy_pending_answer_cannot_bypass_new_question_rules(self):
        qid = self.question("Describe your health")
        pkg = package.load(self.job_id)
        pkg["answer_proposals"][qid] = {"text": "Healthy", "sources": ["summary"]}
        package.save(self.job_id, pkg)
        with self.assertRaises(ResuError):
            package.accept_answers(self.job_id, [qid])
        self.assertNotIn(qid, package.load(self.job_id)["answers"])

    def test_answers_require_explicit_sources_and_do_not_inherit_summary(self):
        qid = self.question()
        for draft in ({"text": "I led a successful team", "sources": []},
                      {"text": "I built Python tools", "sources": ["edu-1"]}):
            with self.assertRaises(ResuError):
                package.propose_answers(self.job_id, [{"question_id": qid, **draft}])
        prof = profile.load()
        prof["summary"] = "Served 999 users."
        profile.save(prof)
        with self.assertRaises(ResuError):
            package.propose_answers(self.job_id, [{"question_id": qid, "text": "Served 999 users.", "sources": ["exp-1-b1"]}])

    def test_resume_bullets_must_cite_bullets(self):
        with self.assertRaises(ResuError):
            package.propose_resume(self.job_id, {"experience": [{"entry": "exp-1", "bullets": [
                {"text": "Led all engineering", "sources": ["exp-1"]}]}]})

    def test_duplicate_drafts_rejected_and_duplicate_accept_ids_safe(self):
        qid = self.question()
        draft = {"question_id": qid, "text": "I build Python services", "sources": ["summary"]}
        with self.assertRaises(ResuError):
            package.propose_answers(self.job_id, [draft, draft])
        package.propose_answers(self.job_id, [draft])
        self.assertEqual(package.accept_answers(self.job_id, [qid, qid]), [qid])

    def test_nested_input_shapes_reject_atomically(self):
        self.prepare()
        before_profile = store.profile_path().read_bytes()
        before_proposal = (store.job_dir(self.job_id) / "proposal.json").read_bytes()
        bad_profiles = [{"contact": {"name": "X", "links": []}}, {"contact": {"name": "X"}, "preferences": "remote"},
                        {"contact": {"name": "X"}, "skills": [{"name": []}]},
                        {"contact": {"name": "X"}, "authorization": [{"country": "US", "authorized": 1}]}]
        for data in bad_profiles:
            with self.subTest(data=data), self.assertRaises(ResuError):
                profile.save(data)
        for data in ({"experience": [42]}, {"summary": 5}, {"education": 5},
                     {"experience": [{"entry": "exp-1", "bullets": "text"}]},
                     {"skills": [{"name": "Python"}]}, {"experiences": []}):
            with self.subTest(data=data), self.assertRaises(ResuError):
                package.propose_resume(self.job_id, data)
        for data in ([5], [{"question_id": "q1", "text": None, "sources": []}],
                     [{"question_id": "q1", "text": "x", "sources": "summary"}]):
            with self.subTest(data=data), self.assertRaises(ResuError):
                package.propose_answers(self.job_id, data)
        for criterion in ({"type": []}, {"type": "skill", "skills": ["Python", 3]},
                          {"type": "years_experience", "years": True}, {"type": "years_experience", "years": float("nan")}):
            with self.subTest(criterion=criterion), self.assertRaises(ResuError):
                jobs.set_requirements(self.job_id, [{"text": "Python", "excerpt": "Python", "criterion": criterion}])
        self.assertEqual(before_profile, store.profile_path().read_bytes())
        self.assertEqual(before_proposal, (store.job_dir(self.job_id) / "proposal.json").read_bytes())

    def test_cli_returns_actionable_shape_error_without_traceback(self):
        result = self.cli("resume", "propose", self.job_id, "--file", "-", data='{"experience": [42]}')
        self.assertEqual(result.returncode, 1)
        self.assertIn("proposal.experience[0]", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_duplicate_json_keys_and_nonfinite_numbers_rejected(self):
        for data in ('{"summary": null, "summary": {}}', '{"summary": NaN}'):
            result = self.cli("resume", "propose", self.job_id, "--file", "-", data=data)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("Traceback", result.stderr)

    def test_invalid_utf8_is_actionable(self):
        path = Path(self._tmp) / "invalid.json"
        path.write_bytes(b"\xff")
        result = self.cli("profile", "save", "--file", str(path))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)

    def test_requirements_cannot_be_skipped_but_explicit_empty_review_allowed(self):
        job_id = jobs.add("X", "Y", "Contact us for details.")["id"]
        package.propose_resume(job_id, fixture("proposal_good.json"))
        package.accept_resume(job_id)
        with self.assertRaises(ResuError):
            package.approve(job_id)
        jobs.set_requirements(job_id, [])
        package.approve(job_id)

    def test_package_check_exit_code_matches_blockers(self):
        result = self.cli("package", "check", self.job_id, "--json")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(json.loads(result.stdout)["blockers"])
        self.prepare()
        result = self.cli("package", "check", self.job_id, "--json")
        self.assertEqual(result.returncode, 0)

    def test_factual_answer_length_blocks_approval(self):
        self.prepare()
        package.add_question(self.job_id, "Full name", True, 3, "chars", None)
        with self.assertRaises(ResuError):
            package.approve(self.job_id)
        for limit in (0, -1):
            with self.assertRaises(ResuError):
                package.add_question(self.job_id, "Email", True, limit, "chars", None)

    def test_changed_evidence_and_overrides_require_confirmation(self):
        checklist.link(self.job_id, "r4", ["exp-1-b1", "exp-1-b2"])
        checklist.override(self.job_id, "r5", "met", "Confirmed with user")
        prof = profile.load()
        prof["experience"][0]["bullets"][0]["text"] = "Assisted with documentation"
        profile.save(prof)
        results = {r["id"]: r for r in checklist.evaluate(jobs.load(self.job_id), profile.load())}
        self.assertEqual(results["r4"]["status"], "unknown")
        self.assertIn("exp-1-b1", results["r4"]["stale_links"])
        self.assertEqual(results["r5"]["status"], "unknown")
        checklist.link(self.job_id, "r4", ["exp-1-b2"])
        self.assertEqual(jobs.load(self.job_id)["evidence"]["r4"]["sources"], ["exp-1-b2"])

    def test_checklist_change_invalidates_approval(self):
        self.prepare()
        package.approve(self.job_id)
        checklist.override(self.job_id, "r5", "met", "User confirmed")
        self.assertEqual(package.review_state(jobs.load(self.job_id), package.load(self.job_id), profile.load()), "stale")
        with self.assertRaises(ResuError):
            track.set_status(self.job_id, "applied")

    def test_old_policy_approval_must_be_reviewed_again(self):
        self.prepare()
        package.approve(self.job_id)
        pkg = package.load(self.job_id)
        pkg["approval"].pop("validation_version")
        package.save(self.job_id, pkg, content_changed=False)
        with self.assertRaises(ResuError):
            track.set_status(self.job_id, "applied")

    def test_old_factual_mapping_is_rechecked_before_confirmation(self):
        self.prepare()
        qid = self.question("What is your manager's email?")
        job = jobs.load(self.job_id)
        job["questions"][0].update(category="factual", factual_key="email", required=False)
        jobs.save(job)
        answers = package.resolved(job, profile.load(), package.load(self.job_id))["answers"]
        self.assertFalse(answers[0]["resolved"])
        self.assertEqual(answers[0]["text"], "")
        self.assertTrue(package.check(self.job_id)[0])
        with self.assertRaises(ResuError):
            package.confirm_answer(self.job_id, qid)

    def test_new_proposal_warning_does_not_depend_on_clock_resolution(self):
        self.prepare()
        proposal = fixture("proposal_good.json")
        proposal["skills"] = ["Python"]
        package.propose_resume(self.job_id, proposal)
        record = package.load_proposal(self.job_id)
        record["created_at"] = package.load(self.job_id)["resume_accepted_at"]
        store.write_json(store.job_dir(self.job_id) / "proposal.json", record)
        self.assertTrue(any("not been accepted" in w for w in package.check(self.job_id)[1]))

    def test_unsupported_schema_refuses_to_overwrite_data(self):
        prof = profile.load()
        prof["_meta"]["schema"] = 999
        store.write_json(store.profile_path(), prof)
        original = store.profile_path().read_bytes()
        with self.assertRaises(ResuError):
            profile.save(fixture("profile.json"))
        self.assertEqual(original, store.profile_path().read_bytes())

    def test_new_profile_diff_discloses_bullets_and_fields(self):
        changes = profile.diff(None, profile.load())
        self.assertTrue(any("1,200 internal users" in change for change in changes))
        self.assertTrue(any("Software Engineering Intern" in change for change in changes))

    def test_sponsorship_does_not_prove_eligibility(self):
        status, _ = checklist._authorization({"country": "US", "sponsorship_available": True},
                                             {"authorization": [{"country": "US", "authorized": False}]})
        self.assertEqual(status, "unknown")

    def test_dates_are_real_calendar_dates(self):
        for date in ("2026-02-30", "2026-01-00", "0000", "2026-04-31"):
            self.assertFalse(is_valid_date(date), date)
            self.assertIsNone(date_key(date))
        self.assertTrue(is_valid_date("2024-02-29"))
        self.assertEqual(date_key("2026-02", True), (2026, 2, 28))

    def test_demo_isolated_and_refuses_existing_output(self):
        before = store.profile_path().read_bytes()
        destination = Path(self._tmp) / "separate-demo"
        output = demo.create(str(destination))
        self.assertEqual(os.environ["RESUSKILL_HOME"], self._tmp)
        self.assertEqual(store.profile_path().read_bytes(), before)
        self.assertTrue(Path(output["review"]).exists())
        self.assertTrue(any("q2" in b for b in output["blockers"]))
        with self.assertRaises(ResuError):
            demo.create(str(destination))

    def test_review_displays_accepted_and_replacement_answer_with_sources(self):
        qid = self.question()
        package.propose_answers(self.job_id, [{"question_id": qid, "text": "I build Python services", "sources": ["summary"]}])
        package.accept_answers(self.job_id, [])
        package.propose_answers(self.job_id, [{"question_id": qid, "text": "I enjoy building Python tools", "sources": ["summary"]}])
        output = render.render(self.job_id)
        html = Path(output["review"]).read_text(encoding="utf-8")
        for text in ("I build Python services", "I enjoy building Python tools", "Replacement draft", profile.load()["summary"]):
            self.assertIn(text, html)

    def test_installer_copy_runs_from_path_with_spaces_and_rejects_conflict(self):
        if os.name == "nt" or not shutil.which("bash"):
            self.skipTest("Bash installer is tested on Unix; Windows supports manual copy")
        config = Path(self._tmp) / "claude config"
        env = {**os.environ, "CLAUDE_CONFIG_DIR": str(config)}
        result = subprocess.run(["bash", str(ROOT / "install.sh"), "claude", "--copy"],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = config / "skills/resuskill"
        self.assertFalse(list(installed.rglob("*.pyc")))
        result = subprocess.run([sys.executable, str(installed / "scripts/resuskill.py"), "demo", "--output",
                                 str(Path(self._tmp) / "installed demo"), "--json"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(Path(json.loads(result.stdout)["review"]).exists())
        conflict = subprocess.run(["bash", str(ROOT / "install.sh"), "claude", "--copy"],
                                  env=env, capture_output=True, text=True)
        self.assertEqual(conflict.returncode, 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
