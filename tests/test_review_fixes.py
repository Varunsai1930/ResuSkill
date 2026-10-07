"""Regression tests for issues found in code review."""

import unittest

from helpers import IsolatedHome

from resuskill_core import checklist, jobs, skills, validate


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
