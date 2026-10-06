import copy

from helpers import IsolatedHome, fixture

from resuskill_core import checklist, jobs, profile
from resuskill_core.util import ResuError


def by_id(results):
    return {r["id"]: r for r in results}


class RequirementTests(IsolatedHome):
    def test_unsupported_excerpt_rejects_whole_set(self):
        job_id = self.seed(with_requirements=False)
        reqs = fixture("requirements.json")
        reqs[0]["excerpt"] = "Ten years of Java required."
        with self.assertRaises(ResuError):
            jobs.set_requirements(job_id, reqs)
        self.assertEqual(jobs.load(job_id)["requirements"], [])
        self.assertEqual(jobs.load(job_id)["revision"], 1)

    def test_excerpt_matching_ignores_quote_style_and_spacing(self):
        job_id = self.seed(with_requirements=False)
        reqs = [{"text": "Bachelor's", "excerpt": "Pursuing a  Bachelor’s degree", "criterion": None}]
        job = jobs.set_requirements(job_id, reqs)
        self.assertEqual(len(job["requirements"]), 1)

    def test_invalid_criterion_is_rejected(self):
        job_id = self.seed(with_requirements=False)
        reqs = [{"text": "x", "excerpt": "Experience with Rust.", "criterion": {"type": "degree", "level": "wizard"}}]
        with self.assertRaises(ResuError):
            jobs.set_requirements(job_id, reqs)


class ChecklistTests(IsolatedHome):
    def evaluate(self, job_id):
        return by_id(checklist.evaluate(jobs.load(job_id), profile.load()))

    def test_expected_statuses(self):
        results = self.evaluate(self.seed())
        self.assertEqual(results["r1"]["status"], "met")       # Python + SQL listed
        self.assertEqual(results["r2"]["status"], "met")       # pursuing B.S. CS
        self.assertEqual(results["r3"]["status"], "met")       # authorized, no sponsorship needed
        self.assertEqual(results["r4"]["status"], "unknown")   # experience needs evidence
        self.assertEqual(results["r5"]["status"], "unknown")   # Java/Kafka missing, not denied
        self.assertEqual(results["r6"]["status"], "unmet")     # Rust explicitly absent
        self.assertEqual(results["r7"]["status"], "met")

    def test_missing_information_stays_unknown(self):
        data = fixture("profile.json")
        data["authorization"] = []
        data["education"] = []
        profile.save(data)
        job = jobs.add("Demo Corp", "Intern", fixture("job.txt"))
        jobs.set_requirements(job["id"], fixture("requirements.json"))
        results = self.evaluate(job["id"])
        self.assertEqual(results["r2"]["status"], "unknown")
        self.assertEqual(results["r3"]["status"], "unknown")

    def test_explicit_conflicts_are_unmet(self):
        data = fixture("profile.json")
        data["authorization"] = [{"country": "US", "authorized": True, "requires_sponsorship": True}]
        data["preferences"]["work_mode"] = "remote"
        profile.save(data)
        job = jobs.add("Demo Corp", "Intern", fixture("job.txt"))
        jobs.set_requirements(job["id"], fixture("requirements.json"))
        results = self.evaluate(job["id"])
        self.assertEqual(results["r3"]["status"], "unmet")
        self.assertEqual(results["r7"]["status"], "unmet")

    def test_lower_degree_is_unmet(self):
        data = fixture("profile.json")
        data["education"][0]["degree"] = "Associate of Science"
        profile.save(data)
        job = jobs.add("Demo Corp", "Intern", fixture("job.txt"))
        jobs.set_requirements(job["id"], fixture("requirements.json"))
        self.assertEqual(self.evaluate(job["id"])["r2"]["status"], "unmet")

    def test_confirmed_evidence_makes_experience_met(self):
        job_id = self.seed()
        checklist.link(job_id, "r4", ["exp-1-b1"])
        result = self.evaluate(job_id)["r4"]
        self.assertEqual(result["status"], "met")
        self.assertEqual(result["evidence"][0]["id"], "exp-1-b1")

    def test_evidence_link_rejects_unknown_source(self):
        job_id = self.seed()
        with self.assertRaises(ResuError):
            checklist.link(job_id, "r4", ["exp-9-b9"])

    def test_override_requires_reason_and_is_reported(self):
        job_id = self.seed()
        with self.assertRaises(ResuError):
            checklist.override(job_id, "r5", "met", "")
        checklist.override(job_id, "r5", "met", "Used Kafka in a course project not yet in profile")
        result = self.evaluate(job_id)["r5"]
        self.assertEqual(result["status"], "met")
        self.assertIn("User override", result["basis"])
        checklist.override(job_id, "r5", "clear", "")
        self.assertEqual(self.evaluate(job_id)["r5"]["status"], "unknown")

    def test_skill_aliases_match(self):
        data = fixture("profile.json")
        data["skills"] = copy.deepcopy(data["skills"]) + [{"name": "JS"}]
        profile.save(data)
        job = jobs.add("Demo Corp", "Intern", "We use JavaScript daily.")
        jobs.set_requirements(job["id"], [{"text": "JS", "excerpt": "JavaScript", "criterion": {"type": "skill", "skills": ["JavaScript"]}}])
        self.assertEqual(self.evaluate(job["id"])["r1"]["status"], "met")
