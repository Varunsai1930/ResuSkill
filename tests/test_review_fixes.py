"""Regression tests for issues found in code review."""

import os
import subprocess
import sys
import unittest

from helpers import ROOT, IsolatedHome

from resuskill_core import checklist, jobs, package, profile, questions, render, skills, validate
from resuskill_core.util import ResuError


class ChecklistMatchingTests(unittest.TestCase):
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
