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
        self.assertEqual(result["queries"][0], '"Data Analyst" intern OR "entry level" SQL Python Dallas, TX')
        self.assertEqual(result["locations"], ["Dallas, TX"])

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

    def test_remote_only_searches_remote(self):
        self.save(preferences={"roles": ["Data Analyst"], "locations": ["Austin"], "work_mode": "remote"})
        self.assertEqual(search.terms()["locations"], ["Remote"])

    def test_query_cap_keeps_every_role_and_warns(self):
        self.save(preferences={"roles": ["Data Analyst", "BI Analyst", "Analytics Engineer"],
                               "locations": ["Austin", "Dallas"], "work_mode": "any"})
        result = search.terms(max_queries=4)
        self.assertEqual(len(result["queries"]), 4)
        for role in ("Data Analyst", "BI Analyst", "Analytics Engineer"):
            self.assertTrue(any(f'"{role}"' in q for q in result["queries"]), role)
        self.assertTrue(any("5 queries left out" in w for w in result["warnings"]))
        with self.assertRaises(ResuError):
            search.terms(max_queries=0)

    def test_contact_location_fallback_drops_street_and_postal_code(self):
        data = fixture("profile.json")
        data["contact"]["location"] = "12 Oak St, Austin, TX 78701"
        data["preferences"] = {"roles": ["Analyst"], "locations": [], "work_mode": "onsite"}
        profile.save(data)
        result = search.terms()
        self.assertEqual(result["locations"], ["Austin"])
        self.assertNotIn("Oak", json.dumps(result))

    def test_fallback_titles_are_most_recent_first(self):
        data = fixture("profile.json")
        data["preferences"]["roles"] = []
        old = copy.deepcopy(data["experience"][0])
        old.update(title="Marketing Intern", start="2019-06", end="2019-08")
        current = copy.deepcopy(data["experience"][0])
        current.update(organization="Later Co", title="Data Analyst", start="2025-01", end="present")
        data["experience"] = [old, data["experience"][0], current]
        profile.save(data)
        self.assertEqual(search.terms()["roles"], ["Data Analyst", "Software Engineering Intern"])

    def test_further_degree_after_completed_one_gives_no_level(self):
        data = fixture("profile.json")
        done = copy.deepcopy(data["education"][0])
        done.update(degree="B.A.", start="2010-08", end="2014-05")
        data["education"].append(done)
        profile.save(data)
        result = search.terms(["Analyst"])
        self.assertIsNone(result["level"]["hint"])
        self.assertNotIn("intern", result["queries"][0])

    def test_quotes_in_roles_are_removed(self):
        self.save()
        for role in ('Analyst "Data"', "Analyst \u201cData\u201d"):
            self.assertTrue(search.terms([role])["queries"][0].startswith('"Analyst Data" '), role)

    def test_high_school_or_associate_keeps_student_hint(self):
        data = fixture("profile.json")
        for degree in ("High School Diploma", "A.A."):
            earlier = copy.deepcopy(data["education"][0])
            earlier.update(degree=degree, field="", start="2019-08", end="2023-05")
            data["education"].append(earlier)
        profile.save(data)
        self.assertEqual(search.terms()["level"]["hint"], "student")

    def test_query_cap_keeps_remote_and_every_role(self):
        self.save(preferences={"roles": ["Data Analyst", "BI Analyst", "Analytics Engineer"],
                               "locations": ["Austin", "Dallas"], "work_mode": "any"})
        queries = search.terms(max_queries=6)["queries"]
        for term in ("Data Analyst", "BI Analyst", "Analytics Engineer", "Austin", "Dallas", "Remote"):
            self.assertTrue(any(term in q for q in queries), term)

    def test_street_names_without_numbers_are_dropped(self):
        data = fixture("profile.json")
        data["preferences"] = {"roles": ["Analyst"], "locations": [], "work_mode": "onsite"}
        for location, city in (("Baker Street, London", "London"),
                               ("Rosewood Apartments, Austin, TX", "Austin, TX")):
            data["contact"]["location"] = location
            profile.save(copy.deepcopy(data))
            self.assertEqual(search.terms()["locations"], [city], location)

    def test_filtered_contact_location_gets_specific_warning(self):
        data = fixture("profile.json")
        data["contact"]["location"] = "560001"
        data["preferences"] = {"roles": ["Analyst"], "locations": [], "work_mode": "onsite"}
        profile.save(data)
        result = search.terms()
        self.assertEqual(result["locations"], [])
        self.assertTrue(any("no usable city" in w for w in result["warnings"]))

    def test_requires_profile(self):
        with self.assertRaises(ResuError):
            search.terms()
