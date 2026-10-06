from helpers import IsolatedHome, fixture

from resuskill_core import jobs, profile, validate
from resuskill_core.skills import find_terms
from resuskill_core.util import ResuError


def one_bullet(text, sources, entry="exp-1"):
    return {"experience": [{"entry": entry, "bullets": [{"text": text, "sources": sources}]}]}


class ProposalValidationTests(IsolatedHome):
    def setUp(self):
        super().setUp()
        self.job_id = self.seed()
        self.prof = profile.load()
        self.job = jobs.load(self.job_id)

    def assertRejected(self, proposal, fragment):
        with self.assertRaises(ResuError) as ctx:
            validate.validate_proposal(self.prof, self.job, proposal)
        details = " ".join(ctx.exception.details)
        self.assertIn(fragment, details)

    def test_good_proposal_passes(self):
        clean, warnings = validate.validate_proposal(self.prof, self.job, fixture("proposal_good.json"))
        self.assertEqual(clean["experience"][0]["entry"], "exp-1")
        self.assertEqual(clean["education"], ["edu-1"])
        self.assertEqual(warnings, [])

    def test_python_only_source_never_gains_java(self):
        self.assertRejected(one_bullet("Built a Java REST API serving 1,200 users", ["exp-1-b1"]), "Java")

    def test_new_metric_rejected(self):
        self.assertRejected(one_bullet("Reduced report time by 60% using PostgreSQL indexes", ["exp-1-b2"]), "60")

    def test_new_year_rejected(self):
        self.assertRejected(one_bullet("Wrote unit tests for the billing module in 2021", ["exp-1-b3"]), "2021")

    def test_number_words_rejected(self):
        self.assertRejected(one_bullet("Wrote unit tests for twelve billing modules", ["exp-1-b3"]), "12")

    def test_credential_rejected(self):
        self.assertRejected(one_bullet("Certified engineer who wrote unit tests for billing", ["exp-1-b3"]), "certification")

    def test_cross_entry_source_rejected(self):
        self.assertRejected(one_bullet("Used by 3 student clubs", ["proj-1-b2"]), "different entry")

    def test_unknown_source_rejected(self):
        self.assertRejected(one_bullet("Wrote tests", ["exp-1-b99"]), "unknown sources")

    def test_missing_sources_rejected(self):
        self.assertRejected(one_bullet("Wrote tests", []), "cite at least one")

    def test_skill_not_in_profile_rejected(self):
        self.assertRejected({"skills": ["Python", "Kubernetes"]}, "Kubernetes")

    def test_entry_technology_allows_mention(self):
        # Flask is in the entry's technology list even though bullet 3 never says it.
        validate.validate_proposal(self.prof, self.job, one_bullet("Wrote Flask unit tests for the billing module", ["exp-1-b3"]))

    def test_formatting_of_numbers_is_tolerated(self):
        validate.validate_proposal(self.prof, self.job, one_bullet("Served reporting data to 1200 internal users via a Flask REST API", ["exp-1-b1"]))

    def test_summary_must_cite_sources(self):
        self.assertRejected({"summary": {"text": "Backend engineer", "sources": []}}, "summary")


class AnswerValidationTests(IsolatedHome):
    def test_answer_checks_length_and_claims(self):
        job_id = self.seed()
        prof, job = profile.load(), jobs.load(job_id)
        errors = validate.validate_answer(prof, job, "I have 5 years of Kafka experience", ["exp-1-b1"], 5, "words")
        joined = " ".join(errors)
        self.assertIn("5", joined)
        self.assertIn("Kafka", joined)
        self.assertIn("exceeds", joined)

    def test_profile_skill_may_be_mentioned(self):
        job_id = self.seed()
        errors = validate.validate_answer(profile.load(), jobs.load(job_id), "I enjoy working in Python and SQL.", [], None, "chars")
        self.assertEqual(errors, [])


class TermDetectionTests(IsolatedHome):
    def test_common_words_do_not_trigger(self):
        text = "We go to the rest area and react quickly; the spring term ended"
        self.assertEqual(find_terms(text), set())

    def test_symbols_and_aliases(self):
        found = find_terms("Shipped C++ and C# services on k8s with Postgres")
        self.assertTrue({"c++", "c#", "kubernetes", "postgresql"} <= found)

    def test_java_not_found_inside_javascript(self):
        self.assertNotIn("java", find_terms("Wrote JavaScript"))
