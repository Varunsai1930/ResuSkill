"""Regression tests for profile allocation and stored-data audit findings."""

import copy
from pathlib import Path

from helpers import IsolatedHome

from resuskill_core import checklist, jobs, profile, store, track
from resuskill_core.util import ResuError


class StableProfileIdsTests(IsolatedHome):
    def test_identical_entries_keep_distinct_ids_on_unchanged_save(self):
        raw = {"contact": {"name": "Candidate"},
               "projects": [{"name": "Course project"}, {"name": "Course project"}]}
        first, _, _ = profile.save(raw)
        second, changes, _ = profile.save(raw)
        self.assertEqual(second, first)
        self.assertEqual(changes, [])

    def test_identical_bullets_keep_distinct_ids_on_unchanged_save(self):
        raw = {"contact": {"name": "Candidate"}, "experience": [
            {"organization": "Company", "bullets": ["Same accomplishment", "Same accomplishment"]}]}
        first, _, _ = profile.save(raw)
        second, changes, _ = profile.save(raw)
        self.assertEqual(second, first)
        self.assertEqual(changes, [])

    def test_explicit_entry_id_is_reserved_before_implicit_matching(self):
        first, _, _ = profile.save({"contact": {"name": "Candidate"},
                                    "projects": [{"name": "Course project"}]})
        raw = copy.deepcopy(first)
        explicit = raw["projects"][0]
        raw["projects"] = [{"name": "Course project"}, explicit]
        saved, _, _ = profile.save(raw)
        self.assertEqual([e["id"] for e in saved["projects"]], ["proj-2", "proj-1"])

    def test_explicit_bullet_id_is_reserved_before_implicit_matching(self):
        first, _, _ = profile.save({"contact": {"name": "Candidate"}, "experience": [
            {"organization": "Company", "bullets": ["Same accomplishment"]}]})
        raw = copy.deepcopy(first)
        explicit = raw["experience"][0]["bullets"][0]
        raw["experience"][0]["bullets"] = [explicit["text"], explicit]
        saved, _, _ = profile.save(raw)
        self.assertEqual([b["id"] for b in saved["experience"][0]["bullets"]],
                         ["exp-1-b2", "exp-1-b1"])

    def test_malformed_bullet_id_is_rejected_without_overwriting_profile(self):
        first, _, _ = profile.save({"contact": {"name": "Candidate"}})
        raw = copy.deepcopy(first)
        raw["experience"] = [{"id": "exp-1", "organization": "Company",
                              "bullets": [{"id": "exp-1-bgarbage", "text": "An accomplishment"}]}]
        with self.assertRaises(ResuError):
            profile.save(raw)
        self.assertEqual(profile.load(), first)


class StableRequirementIdsTests(IsolatedHome):
    def test_identical_requirements_keep_ids_and_evidence_on_resave(self):
        profile.save({"contact": {"name": "Candidate"}, "skills": ["Python"]})
        job = jobs.add("Company", "Engineer", "Python is required.")
        raw = [{"text": "Python", "excerpt": "Python is required"},
               {"text": "Python", "excerpt": "Python is required"}]
        jobs.set_requirements(job["id"], raw)
        checklist.link(job["id"], "r1", ["skill:python"])
        checklist.override(job["id"], "r2", "met", "User confirmed it")
        saved = jobs.set_requirements(job["id"], raw)
        self.assertEqual([r["id"] for r in saved["requirements"]], ["r1", "r2"])
        self.assertIn("r1", saved["evidence"])
        self.assertIn("r2", saved["overrides"])


class AvailabilityTests(IsolatedHome):
    def evaluate(self, start_date, **criterion):
        return checklist._availability(criterion, {"availability": {"start_date": start_date}})[0]

    def test_start_from_does_not_disqualify_earlier_availability(self):
        self.assertEqual(self.evaluate("2026-02", start_from="2026-03"), checklist.MET)
        self.assertEqual(self.evaluate("2026-03-01", start_from="2026-03-01"), checklist.MET)

    def test_start_from_alone_cannot_confirm_later_availability(self):
        self.assertEqual(self.evaluate("2026-09", start_from="2026-03"), checklist.UNKNOWN)

    def test_partial_availability_overlapping_earliest_start_stays_unknown(self):
        self.assertEqual(self.evaluate("2026", start_from="2026-03"), checklist.UNKNOWN)
        self.assertEqual(self.evaluate("2026-03", start_from="2026-03"), checklist.UNKNOWN)

    def test_availability_between_start_from_and_deadline_is_met(self):
        self.assertEqual(self.evaluate("2026-06", start_from="2026-03", start_by="2026-07"), checklist.MET)
        self.assertEqual(self.evaluate("2026-08", start_from="2026-03", start_by="2026-07"), checklist.UNMET)

    def test_reversed_date_windows_are_rejected_without_changing_job(self):
        job = jobs.add("Company", "Engineer", "Start in 2026.")
        for criterion in (
            {"type": "availability", "start_from": "2026-09", "start_by": "2026-03"},
            {"type": "graduation_window", "from": "2026-09", "to": "2026-03"},
        ):
            with self.subTest(criterion=criterion):
                with self.assertRaises(ResuError):
                    jobs.set_requirements(job["id"], [{"text": "Start date", "excerpt": "Start in 2026",
                                                      "criterion": criterion}])
                self.assertEqual(jobs.load(job["id"]), job)

    def test_overlapping_partial_window_bounds_are_allowed(self):
        job = jobs.add("Company", "Engineer", "Start in 2026.")
        saved = jobs.set_requirements(job["id"], [{"text": "Start date", "excerpt": "Start in 2026",
            "criterion": {"type": "availability", "start_from": "2026", "start_by": "2026-03"}}])
        self.assertEqual(len(saved["requirements"]), 1)


class StoredJsonTests(IsolatedHome):
    def test_damaged_nested_requirements_keep_job_listing_and_tracker_usable(self):
        profile.save({"contact": {"name": "Candidate"}, "skills": ["Python"]})
        healthy = jobs.add("Healthy", "Engineer", "Python required.")
        healthy = jobs.set_requirements(healthy["id"], [{"text": "Python", "excerpt": "Python required",
            "criterion": {"type": "skill", "skills": ["Python"]}}])
        damaged = jobs.add("Damaged", "Engineer", "Python required.")
        requirement = copy.deepcopy(healthy["requirements"][0])
        cases = [["damaged"], [dict(requirement, criterion={"type": "skill", "skills": "Python"})]]
        for field in ("id", "text", "excerpt", "category", "importance"):
            missing = copy.deepcopy(requirement)
            missing.pop(field)
            cases.append([missing])
        for criterion in ({"skills": ["Python"]}, {"type": "skill", "skills": ["Python"]},
                          {"type": "skill", "skills": None, "match": "all"}):
            cases.append([dict(requirement, criterion=criterion)])
        for requirements in cases:
            with self.subTest(requirements=requirements):
                damaged["requirements"] = requirements
                jobs.save(damaged)
                with self.assertRaises(ResuError):
                    jobs.load(damaged["id"])
                problems = []
                self.assertEqual([j["id"] for j in jobs.list_jobs(problems)], [healthy["id"]])
                self.assertEqual(problems[0][0], damaged["id"])
                rows = {r["id"]: r for r in track.rows()}
                self.assertEqual(rows[damaged["id"]]["review"], "unreadable")
                self.assertIn("restore a valid backup", rows[damaged["id"]]["error"])
                self.assertEqual(rows[healthy["id"]]["checklist"]["met"], 1)

    def test_legacy_requirement_with_no_criterion_stays_readable(self):
        job = jobs.add("Company", "Engineer", "Python required.")
        job["requirements"] = [{"id": "r1", "text": "Python", "excerpt": "Python required",
                                "category": "skill", "importance": "required"}]
        jobs.save(job)
        self.assertEqual(jobs.load(job["id"])["requirements"], job["requirements"])

    def test_duplicate_stored_keys_are_rejected(self):
        path = Path(self._tmp) / "data.json"
        path.write_text('{"fact": "first", "fact": "second"}', encoding="utf-8")
        with self.assertRaises(ResuError):
            store.read_json(path)

    def test_nonfinite_stored_numbers_are_rejected(self):
        path = Path(self._tmp) / "data.json"
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                path.write_text('{"number": ' + value + '}', encoding="utf-8")
                with self.assertRaises(ResuError):
                    store.read_json(path)

    def test_unreadable_stored_job_does_not_hide_healthy_jobs(self):
        healthy = jobs.add("Healthy", "Engineer", "Description")
        damaged = jobs.add("Damaged", "Engineer", "Description")
        (store.job_dir(damaged["id"]) / "job.json").write_bytes(b"\xff")
        problems = []
        self.assertEqual([j["id"] for j in jobs.list_jobs(problems)], [healthy["id"]])
        self.assertEqual(problems[0][0], damaged["id"])

    def test_invalid_utf8_input_reports_a_user_error(self):
        path = Path(self._tmp) / "input.json"
        path.write_bytes(b"\xff")
        for loader in (store.load_input, store.load_text):
            with self.subTest(loader=loader.__name__):
                with self.assertRaises(ResuError):
                    loader(str(path))

    def test_input_directory_reports_a_user_error(self):
        for loader in (store.load_input, store.load_text):
            with self.subTest(loader=loader.__name__):
                with self.assertRaises(ResuError):
                    loader(self._tmp)
