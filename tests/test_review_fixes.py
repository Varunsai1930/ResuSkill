"""Regression tests for issues found in code review."""

import unittest

from helpers import IsolatedHome

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
