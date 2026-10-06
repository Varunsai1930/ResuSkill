import copy
import hashlib
from pathlib import Path
from unittest import mock

from helpers import IsolatedHome, fixture

from resuskill_core import package, profile, questions, render, store, track
from resuskill_core.util import ResuError


def digest(folder):
    h = hashlib.sha256()
    for path in sorted(folder.iterdir()):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


class QuestionTests(IsolatedHome):
    def test_classification(self):
        cases = {
            "Are you legally authorized to work in the United States?": ("sensitive_factual", "authorization"),
            "Will you require visa sponsorship?": ("sensitive_factual", "sponsorship"),
            "Do you identify as a veteran?": ("sensitive", None),
            "What are your salary expectations?": ("sensitive", None),
            "Why do you want to work here?": ("open", None),
            "What is your expected graduation date?": ("factual", "graduation_date"),
            "Are you willing to relocate?": ("unknown", None),
        }
        for text, expected in cases.items():
            self.assertEqual(questions.classify(text), expected, text)


class PackageFlowTests(IsolatedHome):
    def setUp(self):
        super().setUp()
        self.job_id = self.seed()

    def prepare(self):
        package.propose_resume(self.job_id, fixture("proposal_good.json"))
        package.accept_resume(self.job_id)
        package.add_question(self.job_id, "Are you legally authorized to work in the United States?", True, None, "chars", None)
        package.add_question(self.job_id, "What is your gender?", False, None, "chars", None)
        package.add_question(self.job_id, "Why are you interested in this role?", True, 400, "chars", None)
        package.add_question(self.job_id, "Expected graduation date", True, None, "chars", None)

    def answer_all(self):
        drafts = fixture("answers.json")
        drafts[0]["question_id"] = "q3"
        package.propose_answers(self.job_id, drafts)
        package.accept_answers(self.job_id, [])
        package.confirm_answer(self.job_id, "q1")
        package.set_answer(self.job_id, "q2", None, skip=True)

    def test_proposal_does_not_touch_accepted_resume(self):
        package.propose_resume(self.job_id, fixture("proposal_good.json"))
        package.accept_resume(self.job_id)
        accepted = copy.deepcopy(package.load(self.job_id)["resume"])
        other = fixture("proposal_good.json")
        other["skills"] = ["Python"]
        package.propose_resume(self.job_id, other)
        self.assertEqual(package.load(self.job_id)["resume"], accepted)

    def test_rejected_proposal_keeps_previous_proposal(self):
        package.propose_resume(self.job_id, fixture("proposal_good.json"))
        with self.assertRaises(ResuError):
            package.propose_resume(self.job_id, fixture("proposal_bad.json"))
        self.assertEqual(package.load_proposal(self.job_id)["proposal"]["skills"][0], "Python")

    def test_approval_blocked_until_required_and_sensitive_resolved(self):
        self.prepare()
        blockers, _ = package.check(self.job_id)
        self.assertTrue(any(b.startswith("q1") for b in blockers))
        self.assertTrue(any(b.startswith("q2") for b in blockers))
        self.assertTrue(any(b.startswith("q3") for b in blockers))
        self.assertFalse(any(b.startswith("q4") for b in blockers))  # factual, from profile
        with self.assertRaises(ResuError):
            package.approve(self.job_id)
        self.answer_all()
        self.assertEqual(package.check(self.job_id)[0], [])
        package.approve(self.job_id)

    def test_required_question_cannot_be_skipped(self):
        self.prepare()
        with self.assertRaises(ResuError):
            package.set_answer(self.job_id, "q1", None, skip=True)

    def test_ai_drafts_only_for_open_questions(self):
        self.prepare()
        with self.assertRaises(ResuError):
            package.propose_answers(self.job_id, [{"question_id": "q1", "text": "Yes", "sources": []}])

    def test_editing_clears_approval_and_profile_change_makes_stale(self):
        self.prepare()
        self.answer_all()
        package.approve(self.job_id)
        from resuskill_core import jobs

        job, prof = jobs.load(self.job_id), profile.load()
        self.assertEqual(package.review_state(job, package.load(self.job_id), prof), "approved")
        package.set_answer(self.job_id, "q3", "I like analytics work.")
        self.assertEqual(package.review_state(job, package.load(self.job_id), prof), "draft")
        package.approve(self.job_id)
        edited = copy.deepcopy(prof)
        edited["summary"] = "Updated summary."
        profile.save(edited)
        self.assertEqual(package.review_state(job, package.load(self.job_id), profile.load()), "stale")

    def test_applied_requires_current_approval(self):
        self.prepare()
        with self.assertRaises(ResuError):
            track.set_status(self.job_id, "applied")

    def test_snapshot_survives_profile_edits(self):
        self.prepare()
        self.answer_all()
        package.approve(self.job_id)
        with mock.patch.object(render, "find_browser", return_value=None):
            job = track.set_status(self.job_id, "applied", "submitted")
        folder = store.job_dir(self.job_id) / "snapshots" / job["tracking"]["snapshot"]
        before = digest(folder)
        edited = copy.deepcopy(profile.load())
        edited["experience"][0]["bullets"][1]["text"] = "Reduced report time by 40% with PostgreSQL indexes"
        profile.save(edited)
        render.render(self.job_id)
        self.assertEqual(digest(folder), before)
        self.assertIn("35%", (folder / "resume.html").read_text())
        with self.assertRaises(ResuError):
            track.set_status(self.job_id, "applied")

    def test_sensitive_answers_never_enter_bank(self):
        self.prepare()
        self.answer_all()
        with self.assertRaises(ResuError):
            package.bank_save(self.job_id, "q1")
        entry = package.bank_save(self.job_id, "q3")
        self.assertEqual(questions.bank()[0]["id"], entry["id"])


class RenderTests(IsolatedHome):
    def test_html_is_escaped(self):
        data = fixture("profile.json")
        data["experience"][0]["bullets"][0] = "Built <script>alert(1)</script> dashboards"
        profile.save(data)
        prof = profile.load()
        resume = {"experience": [{"entry": "exp-1", "bullets": [{"text": "Built <script>alert(1)</script> dashboards", "sources": ["exp-1-b1"]}]}],
                  "education": [], "skills": [], "certifications": []}
        html = render.resume_html(prof, resume, "x")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_trusted_fields_come_from_profile(self):
        job_id = self.seed()
        package.propose_resume(job_id, fixture("proposal_good.json"))
        package.accept_resume(job_id)
        outputs = render.render(job_id)
        html = Path(outputs["resume"]).read_text(encoding="utf-8")
        for text in ("Jordan Example", "Sample Analytics", "Jun 2024", "Example State University", "B.S."):
            self.assertIn(text, html)

    def test_long_profile_renders_all_entries(self):
        data = fixture("profile.json")
        base = data["experience"][0]
        data["experience"] = [dict(copy.deepcopy(base), organization=f"Company {i}") for i in range(12)]
        profile.save(data)
        prof = profile.load()
        resume = {"experience": [{"entry": e["id"], "bullets": [{"text": e["bullets"][0]["text"], "sources": [e["bullets"][0]["id"]]}]} for e in prof["experience"]],
                  "education": ["edu-1"], "skills": ["Python"], "certifications": []}
        html = render.resume_html(prof, resume, "x")
        self.assertEqual(html.count('class="entry"'), 13)
        self.assertIn("break-inside: avoid", html)
