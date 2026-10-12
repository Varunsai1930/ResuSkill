"""Regression tests for issues found in code review."""

import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from helpers import ROOT, IsolatedHome

from resuskill_core import checklist, jobs, package, profile, questions, render, skills, validate
from resuskill_core.util import ResuError


class ChecklistMatchingTests(unittest.TestCase):
    def test_degree_status_requires_unambiguous_dates(self):
        prof = {"education": [{"id": "edu-1", "institution": "University", "degree": "BS"}]}
        criterion = {"level": "bachelor", "fields": [], "status": "pursuing"}
        # The current year/month could describe a past or future graduation.
        cases = [
            ("2026", checklist.UNKNOWN, checklist.UNKNOWN),
            ("2026-10", checklist.UNKNOWN, checklist.UNKNOWN),
            ("2025", checklist.UNKNOWN, checklist.MET),
            ("2026-09", checklist.UNKNOWN, checklist.MET),
            ("2027", checklist.MET, checklist.UNKNOWN),
            ("2026-11", checklist.MET, checklist.UNKNOWN),
            ("2026-10-10", checklist.UNKNOWN, checklist.MET),
            ("2026-10-11", checklist.UNKNOWN, checklist.MET),
            ("2026-10-12", checklist.MET, checklist.UNKNOWN),
            ("present", checklist.MET, checklist.UNKNOWN),
            (None, checklist.UNKNOWN, checklist.UNKNOWN),
        ]
        with patch("resuskill_core.checklist.today_key", return_value=(2026, 10, 11)):
            for end, pursuing, completed in cases:
                prof["education"][0]["end"] = end
                for status, expected in (("pursuing", pursuing), ("completed", completed), ("any", checklist.MET)):
                    with self.subTest(end=end, status=status):
                        criterion["status"] = status
                        self.assertEqual(checklist._degree(criterion, prof)[0], expected)

    def test_degree_field_needs_whole_words(self):
        self.assertFalse(checklist._field_matches("Economics", ["CS"]))
        self.assertFalse(checklist._field_matches("Art", ["Computer Science and Artificial Intelligence"]))
        self.assertTrue(checklist._field_matches("Computer Science", ["Computer Science"]))
        self.assertTrue(checklist._field_matches("Computer Science and Engineering", ["Computer Science"]))

    def test_location_needs_whole_words(self):
        prof = {"preferences": {"locations": ["US"]}, "contact": {"location": "New York, NY"}}
        self.assertEqual(checklist._location({"locations": ["Australia"]}, prof)[0], checklist.UNKNOWN)
        self.assertEqual(checklist._location({"locations": ["Germany"]}, prof)[0], checklist.UNKNOWN)
        self.assertEqual(checklist._location({"locations": ["New York"]}, prof)[0], checklist.MET)


    def test_partial_dates_are_unknown_when_ambiguous(self):
        grad = lambda end, **crit: checklist._graduation(crit, {"education": [{"end": end}]})[0]
        self.assertEqual(grad("2026", **{"from": "2026-03"}), checklist.UNKNOWN)
        self.assertEqual(grad("2026", **{"to": "2026-06"}), checklist.UNKNOWN)
        self.assertEqual(grad("2025", **{"from": "2026-03"}), checklist.UNMET)
        self.assertEqual(grad("2026-05", **{"from": "2026-03", "to": "2026-06"}), checklist.MET)
        avail = lambda start: checklist._availability({"start_by": "2026-03"}, {"availability": {"start_date": start}})[0]
        self.assertEqual(avail("2026"), checklist.UNKNOWN)
        self.assertEqual(avail("2026-02"), checklist.MET)
        self.assertEqual(avail("2027"), checklist.UNMET)

class RequirementIdTests(IsolatedHome):
    def test_resave_keeps_ids_and_drops_links_for_changed_requirements(self):
        job_id = jobs.add("Co", "Eng", "Need Python. Need Docker. Need Kubernetes.")["id"]
        jobs.set_requirements(job_id, [{"text": "Python", "excerpt": "Need Python"}, {"text": "Docker", "excerpt": "Need Docker"}])
        checklist.override(job_id, "r2", "met", "has Docker")
        job = jobs.set_requirements(job_id, [{"text": "Docker", "excerpt": "Need Docker"}, {"text": "Kubernetes", "excerpt": "Need Kubernetes"}])
        ids = {r["text"]: r["id"] for r in job["requirements"]}
        self.assertEqual(ids, {"Docker": "r2", "Kubernetes": "r3"})
        self.assertIn("r2", job["overrides"])
        job = jobs.set_requirements(job_id, [{"id": "r2", "text": "Docker 3+ years", "excerpt": "Need Docker"}])
        self.assertEqual(job["overrides"], {})
        job = jobs.set_requirements(job_id, [{"text": "Python", "excerpt": "Need Python"}])
        self.assertEqual(job["requirements"][0]["id"], "r4")


    def test_string_where_a_list_is_expected_is_rejected(self):
        job_id = jobs.add("Co", "Eng", "Need Python.")["id"]
        for crit in ({"type": "skill", "skills": "Python"},
                     {"type": "degree", "level": "bachelor", "fields": "Computer Science"},
                     {"type": "location", "locations": "Austin"}):
            with self.assertRaises(ResuError):
                jobs.set_requirements(job_id, [{"text": "x", "excerpt": "Need Python", "criterion": crit}])
        with self.assertRaises(ResuError):
            profile.save({"contact": {"name": "A"}, "preferences": {"roles": "Backend Engineer"}})

class FabricationCheckTests(unittest.TestCase):
    def test_professional_credentials_are_not_interchangeable(self):
        for source in ("CPA", "PMP", "CFA", "CISSP", "CCNA"):
            for claim in ("CPA", "PMP", "CFA", "CISSP", "CCNA"):
                with self.subTest(source=source, claim=claim):
                    problems = validate.claim_problems(claim.lower(), [source], set(), ())
                    self.assertEqual(bool(problems), source != claim)

    def test_slash_separated_technologies_are_detected(self):
        self.assertEqual(skills.find_terms("Built APIs in Python/Django"), {"python", "django"})
        self.assertEqual(skills.find_terms("C/C++ and CI/CD"), {"c", "c++", "continuous integration"})

    def test_plural_number_words_count_as_numbers(self):
        self.assertEqual(validate.numbers("used by millions of users"), {"1000000"})
        self.assertEqual(validate.numbers("thousands of requests, dozens of teams"), {"1000", "12"})
        problems = validate.claim_problems("Dashboard used by millions of users", ["Built a dashboard for users"], set(), ())
        self.assertTrue(problems)

    def test_degree_claims_are_compared_by_level(self):
        self.assertIn("master's degree", validate.credentials("M.S. graduate"))
        self.assertIn("master's degree", validate.credentials("Master of Science in CS"))
        self.assertIn("master's degree", validate.credentials("Master’s degree"))
        self.assertIn("bachelor's degree", validate.credentials("B.Tech in ECE"))
        problems = validate.claim_problems("Master's degree holder", ["Bachelor's degree · Computer Science"], set(), ())
        self.assertTrue(any("master's degree" in p for p in problems))
        self.assertEqual(validate.claim_problems("Bachelor of Science graduate", ["B.S. · Computer Science"], set(), ()), [])


class ProfileIdTests(IsolatedHome):
    def test_identical_certification_input_keeps_approved_package_valid(self):
        data = {"contact": {"name": "A"}, "certifications": [{"name": "CPA", "issuer": "Board", "date": "2020"}]}
        first, _, _ = profile.save(data)
        job_id = jobs.add("Co", "Role", "Accounting")["id"]
        jobs.set_requirements(job_id, [])
        package.propose_resume(job_id, {"summary": {"text": "CPA", "sources": ["cert-1"]}})
        package.accept_resume(job_id)
        package.approve(job_id)
        again, changes, _ = profile.save(data)
        self.assertEqual(again, first)
        self.assertEqual(changes, [])
        self.assertEqual(package.check(job_id)[0], [])
        self.assertEqual(package.review_state(jobs.load(job_id), package.load(job_id), again), package.APPROVED)

    def test_certification_ids_survive_reordering_and_are_not_reissued(self):
        data = {"contact": {"name": "A"}, "certifications": [{"name": "CPA"}, {"name": "PMP"}]}
        profile.save(data)
        data["certifications"].reverse()
        reordered, _, _ = profile.save(data)
        self.assertEqual([c["id"] for c in reordered["certifications"]], ["cert-2", "cert-1"])
        data["certifications"] = [{"name": "PMP"}]
        profile.save(data)
        data["certifications"].append({"name": "CFA"})
        changed, _, _ = profile.save(data)
        self.assertEqual([c["id"] for c in changed["certifications"]], ["cert-2", "cert-3"])

    def test_matching_certifications_preserve_distinct_and_explicit_ids(self):
        data = {"contact": {"name": "A"}, "certifications": [{"name": "CPA"}, {"name": "CPA"}]}
        first, _, _ = profile.save(data)
        again, _, _ = profile.save(data)
        self.assertEqual(again, first)
        # An implicit match must not consume an ID explicitly supplied later.
        data["certifications"][1]["id"] = "cert-1"
        reserved, _, _ = profile.save(data)
        self.assertEqual([c["id"] for c in reserved["certifications"]], ["cert-2", "cert-1"])

    def test_deleted_bullet_id_is_not_reused(self):
        profile.save({"contact": {"name": "A"}, "experience": [{"organization": "O", "title": "T", "start": "2020", "bullets": ["a", "b", "c"]}]})
        data = profile.load()
        data["experience"][0]["bullets"] = data["experience"][0]["bullets"][:2]
        profile.save(data)
        data = profile.load()
        data["experience"][0]["bullets"].append({"text": "new"})
        prof, _, _ = profile.save(data)
        self.assertEqual([b["id"] for b in prof["experience"][0]["bullets"]], ["exp-1-b1", "exp-1-b2", "exp-1-b4"])


    def test_diff_shows_certification_and_skill_category_edits(self):
        profile.save({"contact": {"name": "A"}, "skills": [{"name": "Python", "category": "Languages"}],
                      "certifications": [{"name": "AWS CCP", "issuer": "AWS", "date": "2023-05"}]})
        data = profile.load()
        data["certifications"][0]["date"] = "2021-05"
        data["skills"][0]["category"] = "Tools"
        new, _ = profile.normalize(data, profile.load())
        changes = profile.diff(profile.load(), new)
        self.assertIn("~ certifications.cert-1.date: 2023-05 -> 2021-05", changes)
        self.assertIn("~ skill Python.category: Languages -> Tools", changes)

class CredentialApprovalTests(IsolatedHome):
    def setUp(self):
        super().setUp()
        profile.save({"contact": {"name": "A"}, "certifications": [{"name": "CPA"}]})
        self.job_id = jobs.add("Co", "Role", "Accounting")["id"]
        jobs.set_requirements(self.job_id, [])

    def test_invented_credential_is_rejected_in_resume_and_answer(self):
        with self.assertRaises(ResuError):
            package.propose_resume(self.job_id, {"summary": {"text": "PMP", "sources": ["cert-1"]}})
        question = package.add_question(self.job_id, "Why do you want this role?", True, None, "chars", None)
        with self.assertRaises(ResuError):
            package.propose_answers(self.job_id, [{"question_id": question["id"], "text": "PMP", "sources": ["cert-1"]}])

    def test_existing_unsupported_resume_cannot_be_reapproved(self):
        package.propose_resume(self.job_id, {"summary": {"text": "CPA", "sources": ["cert-1"]}})
        package.accept_resume(self.job_id)
        pkg = package.load(self.job_id)
        pkg["resume"]["summary"]["text"] = "PMP"
        package.save(self.job_id, pkg)
        self.assertTrue(package.check(self.job_id)[0])
        with self.assertRaises(ResuError):
            package.approve(self.job_id)

    def test_previous_validation_policy_approval_becomes_stale(self):
        package.propose_resume(self.job_id, {"certifications": ["cert-1"]})
        package.accept_resume(self.job_id)
        with patch.object(package, "VALIDATION_VERSION", 2):
            package.approve(self.job_id)
        self.assertEqual(package.review_state(jobs.load(self.job_id), package.load(self.job_id), profile.load()), package.STALE)


class AuthorizationQuestionTests(unittest.TestCase):
    PROF = {"authorization": [{"country": "US", "authorized": True, "requires_sponsorship": False}]}

    def value(self, text):
        return questions.factual_value("authorization", text, self.PROF)

    def test_unlisted_country_is_not_answered_from_another_record(self):
        self.assertIsNone(self.value("Are you authorized to work in Japan?"))
        self.assertIsNone(self.value("Are you authorized to work in Indiana?"))

    def test_known_country_and_unnamed_country_still_resolve(self):
        self.assertEqual(self.value("Are you legally authorized to work in the US?"), "Yes")
        self.assertEqual(self.value("Are you authorized to work in the U.S.?"), "Yes")
        self.assertEqual(self.value("Are you legally authorized to work for any employer?"), "Yes")

    def test_pronoun_us_is_not_the_united_states(self):
        prof = {"authorization": [{"country": "US", "authorized": True, "requires_sponsorship": False},
                                  {"country": "IN", "authorized": False, "requires_sponsorship": True}]}
        sponsorship = lambda text: questions.factual_value("sponsorship", text, prof)
        self.assertEqual(sponsorship("Will you require us to sponsor a visa to work in India?"), "Yes")
        self.assertEqual(sponsorship("Will you require sponsorship to work in the US?"), "No")
        self.assertIsNone(sponsorship("Will you require us to sponsor you?"))  # two records, no country named
        self.assertIsNone(sponsorship("Will you require sponsorship in the US or India?"))


class SensitiveCategoryTests(IsolatedHome):
    def test_sensitive_question_cannot_be_made_open(self):
        job_id = jobs.add("Co", "Eng", "Need Python.")["id"]
        with self.assertRaises(ResuError):
            package.add_question(job_id, "What are your salary expectations?", True, None, "chars", "open")
        package.add_question(job_id, "What are your salary expectations?", True, None, "chars", None)
        with self.assertRaises(ResuError):
            package.set_category(job_id, "q1", "open")
        package.add_question(job_id, "Will you require visa sponsorship?", True, None, "chars", None)
        with self.assertRaises(ResuError):
            package.set_category(job_id, "q2", "factual")
        self.assertEqual(package.set_category(job_id, "q2", "sensitive")["category"], "sensitive")

    def test_personal_yes_no_questions_never_get_ai_drafts(self):
        job_id = jobs.add("Co", "Eng", "Need Python.")["id"]
        for text in ("Are you a U.S. citizen?", "What is your nationality?", "Are you 18 or older?",
                     "Do you hold an active security clearance?", "Have you ever been terminated from a job?"):
            self.assertEqual(questions.classify(text), ("sensitive", None), text)
        question = package.add_question(job_id, "Are you willing to relocate?", True, None, "chars", None)
        with self.assertRaises(ResuError):
            package.set_category(job_id, question["id"], "open")
        with self.assertRaises(ResuError):
            package.add_question(job_id, "Do you have a car?", True, None, "chars", "open")
        with self.assertRaises(ResuError):
            package.add_question(job_id, "Additional information", False, None, "chars", "open")


class StaleAnswerTests(IsolatedHome):
    def test_package_check_revalidates_accepted_ai_answers(self):
        job_id = self.seed()
        package.propose_resume(job_id, {"projects": [{"entry": "proj-1", "bullets": [
            {"text": "Created a Python chat bot that tracks team tasks in SQLite", "sources": ["proj-1-b1"]}]}]})
        package.accept_resume(job_id)
        package.add_question(job_id, "Why do you want this role?", True, None, "chars", None)
        package.propose_answers(job_id, [{"question_id": "q1", "text": "I built an API used by 1,200 people.", "sources": ["exp-1-b1"]}])
        package.accept_answers(job_id, [])
        self.assertEqual(package.check(job_id)[0], [])
        prof = profile.load()
        prof["experience"][0]["bullets"] = [b for b in prof["experience"][0]["bullets"] if b["id"] != "exp-1-b1"]
        profile.save(prof)
        blockers = package.check(job_id)[0]
        self.assertTrue(any(b.startswith("q1: accepted AI answer no longer validates") for b in blockers), blockers)
        with self.assertRaises(ResuError):
            package.approve(job_id)


class RenderStaleTests(IsolatedHome):
    def test_render_reports_entries_removed_from_profile(self):
        job_id = self.seed()
        prof = profile.load()
        entry = prof["projects"][0]
        package.propose_resume(job_id, {"projects": [{"entry": entry["id"], "bullets": [
            {"text": entry["bullets"][0]["text"], "sources": [entry["bullets"][0]["id"]]}]}]})
        package.accept_resume(job_id)
        prof["projects"] = []
        profile.save(prof)
        with self.assertRaises(ResuError) as ctx:
            render.render(job_id)
        self.assertIn(entry["id"], str(ctx.exception))


class EncodingTests(IsolatedHome):
    def run_cli(self, *args, stdin: bytes = b""):
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
        script = ROOT / "skills" / "resuskill" / "scripts" / "resuskill.py"
        return subprocess.run([sys.executable, str(script), *args], input=stdin, capture_output=True, env=env, check=True)

    def test_non_ascii_round_trips_through_stdin_and_stdout(self):
        description = "Need Python \u2265 3 years. Team lead: \u0141ukasz \u6771\u4eac \u2713"
        self.run_cli("job", "add", "--company", "Co", "--title", "Eng", "--description-file", "-", stdin=description.encode("utf-8"))
        shown = self.run_cli("job", "show", "co-eng", "--description").stdout.decode("utf-8")
        self.assertEqual(shown.strip(), description)


class SecondReviewRegressionTests(IsolatedHome):
    def test_spelled_out_and_partial_credentials_need_their_own_evidence(self):
        for claim, source in (("Project Management Professional", "CPA certification"),
                              ("Chartered Financial Analyst", "CPA"),
                              ("CFA charterholder", "CFA Level I candidate"),
                              ("Passed CFA Level III", "Passed CFA Level I")):
            with self.subTest(claim=claim):
                self.assertTrue(validate.claim_problems(claim, [source], set(), ()))
        self.assertEqual(validate.claim_problems("Certified Public Accountant", ["CPA certification"], set(), ()), [])

    def test_damaged_job_files_are_listed_as_unreadable(self):
        from resuskill_core import store, track

        for name, content in (("partial", '{"id": "partial"}'), ("empty", "{}")):
            folder = store.jobs_dir() / name
            folder.mkdir()
            (folder / "job.json").write_text(content, encoding="utf-8")
        rows = {r["id"]: r for r in track.rows()}
        self.assertEqual((rows["partial"]["review"], rows["empty"]["review"]), ("unreadable", "unreadable"))
        with self.assertRaises(ResuError):
            jobs.load("partial")

    def test_corrected_certification_keeps_its_id(self):
        data = {"contact": {"name": "A"}, "certifications": [{"name": "CPA", "issuer": "Board", "date": "2020"}]}
        profile.save(data)
        data["certifications"] = [{"name": "CPA", "issuer": "State Board", "date": "2021"},
                                  {"name": "CPA", "issuer": "Board", "date": "2020"}]
        saved, _, _ = profile.save(data)
        # The unchanged record keeps cert-1; the corrected duplicate gets a new ID.
        self.assertEqual([c["id"] for c in saved["certifications"]], ["cert-2", "cert-1"])
        data["certifications"] = [{"name": "CPA", "issuer": "Board", "date": "2019"}]
        corrected, _, _ = profile.save(data)
        self.assertEqual([c["id"] for c in corrected["certifications"]], ["cert-1"])

    def test_today_is_the_local_calendar_day(self):
        import datetime as dt
        from resuskill_core import util

        self.assertEqual(util.today_key(), dt.date.today().timetuple()[:3])
        self.assertEqual(util.date_span("2024-02"), ((2024, 2, 1), (2024, 2, 29)))
        self.assertIsNone(util.date_span("not a date"))
