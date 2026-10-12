import copy
import json
import subprocess
import sys

from helpers import IsolatedHome, ROOT, fixture

from resuskill_core import profile, search
from resuskill_core.util import ResuError


class SearchTermsTests(IsolatedHome):
    def save(self, **changes):
        data = fixture("profile.json")
        data.update(changes)
        profile.save(data)

    def test_skills_ranked_by_supporting_entries_and_absent_skills_excluded(self):
        self.save()
        result = search.terms()
        names = [s["name"] for s in result["skills"]]
        self.assertEqual(names[0], "Python")
        self.assertEqual(result["skills"][0]["evidence_count"], 2)
        self.assertNotIn("Rust", names)
        self.assertEqual(result["skills_absent"], ["Rust"])
        self.assertEqual(result["query_skills"], names[:3])

    def test_queries_use_preferences_and_never_contact_details(self):
        self.save()
        result = search.terms()
        self.assertEqual(result["role_source"], "preferences")
        self.assertEqual(result["locations"], ["Austin", "Remote"])
        self.assertEqual(len(result["queries"]), 2)
        dumped = json.dumps(result)
        for private in ("Jordan", "jordan@example.com", "555 0100", "linkedin"):
            self.assertNotIn(private, dumped)

    def test_requested_role_location_and_skills_override_defaults(self):
        self.save()
        result = search.terms(["Data Analyst"], ["Dallas, TX"], query_skills=["sql", "python"])
        self.assertEqual(result["role_source"], "request")
        self.assertEqual(result["query_skills"], ["SQL", "Python"])
        self.assertEqual(result["queries"][0], '"Data Analyst" intern OR entry level SQL Python Dallas, TX')
        self.assertIn("Remote", result["locations"])

    def test_query_skills_must_be_confirmed(self):
        self.save()
        for skill in ("Tableau", "Rust"):
            with self.subTest(skill=skill), self.assertRaises(ResuError):
                search.terms(query_skills=[skill])

    def test_role_with_level_word_gets_no_level_suffix(self):
        self.save()
        self.assertEqual(search.terms(["Data Analyst Intern"])["queries"][0],
                         '"Data Analyst Intern" Python Flask PostgreSQL Austin')

    def test_missing_roles_fall_back_to_titles_with_warning(self):
        self.save(preferences={"roles": [], "locations": [], "work_mode": None})
        result = search.terms()
        self.assertEqual(result["role_source"], "experience titles")
        self.assertEqual(result["roles"], ["Software Engineering Intern"])
        self.assertEqual(result["locations"], ["Austin, TX"])
        self.assertTrue(any("past job titles" in w for w in result["warnings"]))
        self.assertTrue(any("Work mode unknown" in w for w in result["warnings"]))

    def test_no_roles_gives_no_queries(self):
        data = fixture("profile.json")
        data["preferences"]["roles"] = []
        for entry in data["experience"]:
            entry["title"] = ""
        profile.save(data)
        result = search.terms()
        self.assertEqual(result["queries"], [])
        self.assertTrue(any("No target roles" in w for w in result["warnings"]))

    def test_level_hint_from_graduation(self):
        self.save()
        self.assertEqual(search.terms()["level"]["hint"], "student")
        data = copy.deepcopy(fixture("profile.json"))
        data["education"][0]["end"] = "2001-05"
        profile.save(data)
        result = search.terms(["Analyst"])
        self.assertIsNone(result["level"]["hint"])
        self.assertEqual(result["queries"][0], '"Analyst" Python Flask PostgreSQL Austin')

    def test_sponsorship_and_unknown_authorization_reported(self):
        self.save(authorization=[{"country": "US", "authorized": False, "requires_sponsorship": True},
                                 {"country": "CA"}])
        result = search.terms()
        self.assertEqual(result["sponsorship_needed"], ["US"])
        self.assertEqual(result["authorization_unknown"], ["CA"])

    def test_cli_text_json_and_rejection(self):
        self.save()
        script = str(ROOT / "skills/resuskill/scripts/resuskill.py")

        def run(*args):
            return subprocess.run([sys.executable, script, "profile", "search-terms", *args],
                                  text=True, encoding="utf-8", capture_output=True)

        text = run("--role", "Data Analyst")
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn('"Data Analyst"', text.stdout)
        data = json.loads(run("--json", "--max-queries", "1").stdout)
        self.assertEqual(len(data["queries"]), 1)
        bad = run("--skill", "Tableau")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("not in profile: Tableau", bad.stderr)

    def test_requires_profile(self):
        with self.assertRaises(ResuError):
            search.terms()
