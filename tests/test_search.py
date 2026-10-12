import copy
import json
import subprocess
import sys
from datetime import date
from unittest import mock

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

    def test_sql_database_use_counts_as_sql_evidence_only_when_sql_is_confirmed(self):
        self.save()
        counts = {s["name"]: s["evidence_count"] for s in search.terms()["skills"]}
        self.assertEqual(counts["SQL"], 2)  # PostgreSQL at the internship, SQLite in the project
        data = fixture("profile.json")
        data["skills"] = [s for s in data["skills"] if s["name"] != "SQL"]
        profile.save(data)
        self.assertNotIn("SQL", [s["name"] for s in search.terms()["skills"]])

    def test_queries_use_preferences_and_never_contact_details(self):
        self.save()
        result = search.terms()
        self.assertEqual(result["role_source"], "preferences")
        self.assertEqual(result["locations"], ["Austin", "Remote United States"])
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
                         '"Data Analyst Intern" Python SQL Flask Austin')

    def test_missing_roles_fall_back_to_titles_with_warning(self):
        self.save(preferences={"roles": [], "locations": [], "work_mode": None})
        result = search.terms()
        self.assertEqual(result["role_source"], "experience titles")
        self.assertEqual(result["roles"], ["Software Engineering Intern"])
        self.assertEqual(result["locations"], [])
        self.assertTrue(any("past job titles" in w for w in result["warnings"]))
        self.assertTrue(any("No location preference" in w for w in result["warnings"]))
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
        self.assertEqual(result["queries"][0], '"Analyst" Python SQL Flask Austin')

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
        result = search.terms(max_queries=1)
        self.assertEqual(result["locations"], ["Remote United States"])
        self.assertIn("Remote United States", result["queries"][0])

    def test_remote_uses_authorized_countries_or_plain_remote(self):
        prefs = {"roles": ["Data Analyst"], "locations": [], "work_mode": "remote"}
        self.save(preferences=prefs, authorization=[{"country": "US", "authorized": False, "requires_sponsorship": True},
                                                    {"country": "CA", "authorized": True, "requires_sponsorship": False},
                                                    {"country": "BR", "authorized": True, "requires_sponsorship": False}])
        self.assertEqual(search.terms()["locations"], ["Remote Canada", "Remote BR"])
        self.save(preferences=prefs, authorization=[{"country": "US"}])
        self.assertEqual(search.terms()["locations"], ["Remote"])

    def test_explicit_locations_keep_remote_only_filter_when_queries_are_capped(self):
        self.save(preferences={"roles": ["Data Analyst"], "locations": ["Austin"], "work_mode": "remote"})
        result = search.terms(locations=["Austin", "Dallas"], max_queries=1)
        self.assertEqual(result["locations"], ["Austin", "Dallas"])
        self.assertEqual(len(result["queries"]), 1)
        self.assertIn("Austin", result["queries"][0])
        self.assertIn("Remote", result["queries"][0])
        self.assertTrue(all("Remote" in q for q in search.terms(locations=["Austin", "Dallas"])["queries"]))

    def test_cli_keeps_remote_and_unknown_level_without_contact_address(self):
        data = fixture("profile.json")
        data["contact"]["location"] = "Private Street, Apartment B"
        data["education"][0]["end"] = str(date.today().year)
        data["preferences"] = {"roles": ["Analyst"], "locations": [], "work_mode": "remote"}
        profile.save(data)
        command = [sys.executable, str(ROOT / "skills/resuskill/scripts/resuskill.py"),
                   "profile", "search-terms", "--location", "Austin", "--max-queries", "1"]
        result = subprocess.run(command + ["--json"], text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIsNone(output["level"]["hint"])
        self.assertIn("Austin", output["queries"][0])
        self.assertIn("Remote", output["queries"][0])
        self.assertNotIn("Private Street", result.stdout)
        self.assertTrue(any("graduation" in w.lower() for w in output["warnings"]))
        text = subprocess.run(command, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn("Level: unknown", text.stdout)
        self.assertIn("Remote", text.stdout)
        self.assertNotIn("Private Street", text.stdout)

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

    def test_contact_addresses_are_not_used_as_search_locations(self):
        for address in ("12 Oak St, Austin, TX 78701", "Oak Street, Austin", "Apartment B, Oak Street"):
            with self.subTest(address=address):
                data = fixture("profile.json")
                data["contact"]["location"] = address
                data["preferences"] = {"roles": ["Analyst"], "locations": [], "work_mode": "onsite"}
                profile.save(data)
                result = search.terms()
                self.assertEqual(result["locations"], [])
                self.assertNotIn("Oak", json.dumps(result))
                self.assertTrue(any("No location preference" in w for w in result["warnings"]))

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

    def test_ongoing_role_precedes_roles_with_future_end_dates(self):
        self.save(preferences={"roles": [], "locations": ["Austin"], "work_mode": "onsite"}, experience=[
            {"organization": "Future Co", "title": "Engineering Fellow", "start": "2026", "end": "2099"},
            {"organization": "Current Co", "title": "Engineering Manager", "start": "2025", "end": "present"},
            {"organization": "Old Co", "title": "Intern", "start": "2010", "end": "2011"},
        ])
        self.assertEqual(search.terms()["roles"], ["Engineering Manager", "Engineering Fellow"])

    def test_role_recency_uses_start_date_when_end_date_is_unknown(self):
        self.save(preferences={"roles": [], "locations": ["Austin"], "work_mode": "onsite"}, experience=[
            {"organization": "Old Co", "title": "Intern", "start": "2010", "end": "2011"},
            {"organization": "New Co", "title": "Engineer", "start": "2025"},
        ])
        self.assertEqual(search.terms()["roles"], ["Engineer", "Intern"])

    def test_graduation_period_including_today_keeps_level_unknown(self):
        with mock.patch.object(search, "today_key", return_value=(2026, 10, 12)):
            for graduation in ("2026", "2026-10", "2026-10-12"):
                with self.subTest(graduation=graduation):
                    self.save(education=[{"institution": "Example University", "degree": "B.S.", "end": graduation}])
                    result = search.terms()
                    self.assertIsNone(result["level"]["hint"])
                    self.assertNotIn("graduated", result["level"]["basis"])
                    self.assertTrue(any("graduation" in w.lower() for w in result["warnings"]))
                    self.assertFalse(any("entry level" in q or "intern" in q for q in result["queries"]))

    def test_unambiguous_graduation_dates_keep_supported_level_hints(self):
        with mock.patch.object(search, "today_key", return_value=(2026, 10, 12)):
            for graduation, expected in (("2026-10-13", "student"), ("2026-10-11", "recent graduate"),
                                         ("2026-09", "recent graduate"), ("2025-10-11", None)):
                with self.subTest(graduation=graduation):
                    self.save(education=[{"institution": "Example University", "degree": "B.S.", "end": graduation}])
                    self.assertEqual(search.terms()["level"]["hint"], expected)

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

    def test_explicit_search_locations_do_not_expose_contact_addresses(self):
        data = fixture("profile.json")
        data["preferences"] = {"roles": ["Analyst"], "locations": [], "work_mode": "onsite"}
        for location, city in (("Baker Street, London", "London"),
                               ("Rosewood Apartments, Austin, TX", "Austin, TX")):
            data["contact"]["location"] = location
            profile.save(copy.deepcopy(data))
            result = search.terms(locations=[city])
            self.assertEqual(result["locations"], [city])
            self.assertNotIn(location, json.dumps(result))

    def test_contact_postal_code_requires_a_search_location(self):
        data = fixture("profile.json")
        data["contact"]["location"] = "560001"
        data["preferences"] = {"roles": ["Analyst"], "locations": [], "work_mode": "onsite"}
        profile.save(data)
        result = search.terms()
        self.assertEqual(result["locations"], [])
        self.assertNotIn("560001", json.dumps(result))
        self.assertTrue(any("No location preference" in w for w in result["warnings"]))

    def test_requires_profile(self):
        with self.assertRaises(ResuError):
            search.terms()

    def test_recent_additional_degree_does_not_reset_career_level(self):
        with mock.patch.object(search, "today_key", return_value=(2026, 10, 12)):
            for field in ("end", "graduation"):
                with self.subTest(field=field):
                    self.save(education=[
                        {"institution": "First University", "degree": "B.S.", "end": "2010-05"},
                        {"institution": "Second University", "degree": "M.S.", field: "2026-09"},
                    ], experience=[
                        {"organization": "Example Co", "title": "Senior Software Engineer",
                         "start": "2011", "end": "present"},
                    ])
                    result = search.terms(["Software Engineer"])
                    self.assertIsNone(result["level"]["hint"])
                    self.assertFalse(any("entry level" in q or "intern" in q for q in result["queries"]))
                    self.assertTrue(any("which level" in w for w in result["warnings"]))

    def test_explicit_mid_level_and_management_titles_keep_their_level(self):
        self.save()
        for role in ("Mid-level Data Analyst", "Mid level Data Analyst", "Engineering Manager",
                     "Director of Engineering", "Head of Data", "VP of Engineering"):
            with self.subTest(role=role):
                queries = search.terms([role])["queries"]
                self.assertTrue(all(q.startswith(f'"{role}" ') for q in queries))
                self.assertFalse(any("entry level" in q or "intern" in q for q in queries))

    def test_requested_level_overrides_graduation_and_any_clears_filters(self):
        self.save()
        result = search.terms(["Data Analyst"], level="senior")
        self.assertEqual(result["level"], {"hint": "senior", "basis": "requested level: senior"})
        self.assertTrue(all('"Data Analyst" senior ' in q for q in result["queries"]))
        result = search.terms(["Data Analyst"], level="any")
        self.assertIsNone(result["level"]["hint"])
        self.assertFalse(any("which level" in w for w in result["warnings"]))
        self.assertFalse(any("entry level" in q or "intern" in q for q in result["queries"]))
        with self.assertRaises(ResuError):
            search.terms(level="made-up")

    def test_cli_accepts_explicit_level_and_rejects_invalid_level(self):
        self.save()
        command = [sys.executable, str(ROOT / "skills/resuskill/scripts/resuskill.py"),
                   "profile", "search-terms", "--role", "Data Analyst", "--json", "--level"]
        result = subprocess.run(command + ["mid"], text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["level"]["hint"], "mid")
        self.assertIn('"mid level"', output["queries"][0])
        invalid = subprocess.run(command + ["made-up"], text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(invalid.returncode, 2)
        self.assertNotIn("Traceback", invalid.stderr)
