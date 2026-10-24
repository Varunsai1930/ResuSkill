from helpers import IsolatedHome, fixture

from resuskill_core import jobs, package, profile, validate
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

    def test_hyphenated_technology_claims_need_evidence(self):
        for text, technology in (
            ('Built Kubernetes-based services', 'Kubernetes'),
            ('Built AWS-powered services', 'Amazon Web Services'),
        ):
            with self.subTest(text=text):
                self.assertRejected(one_bullet(text, ['exp-1-b1']), technology)
        validate.validate_proposal(self.prof, self.job,
                                   one_bullet('Built Python-based services', ['exp-1-b1']))

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
        errors = validate.validate_answer(profile.load(), jobs.load(job_id), "I enjoy working in Python and SQL.",
                                          ["skill:python", "skill:sql"], None, "chars")
        self.assertEqual(errors, [])


class DegreeProgressTests(IsolatedHome):
    def test_unfinished_degrees_cannot_become_held_credentials(self):
        for source, claim in (
            ("Pursuing a Master's degree in Computer Science", "Master's degree holder in Computer Science"),
            ('Studying for a B.S. degree', 'Bachelor of Science degree holder'),
            ('Ph.D. candidate', 'Doctorate holder'),
            ('MBA expected next year', 'MBA holder'),
            ("Master's degree candidate", "Master's degree holder"),
            ('Pursuing a B.S., completed an M.S.', "Bachelor's degree holder"),
            ('Pursuing a B.S. and completed an M.S.', "Bachelor's degree holder"),
            ('Pursuing a B.S. Completed an M.S.', "Bachelor's degree holder"),
            ('M.S., expected 2099, B.S. completed', "Master's degree holder"),
        ):
            with self.subTest(source=source):
                self.assertTrue(validate.claim_problems(claim, [source], set(), ()))
                self.assertEqual(validate.claim_problems(source, [source], set(), ()), [])
        self.assertEqual(validate.claim_problems("Master's degree holder", ["Master of Science graduate"], set(), ()), [])

    def test_mixed_completed_and_pending_degrees_keep_their_own_status(self):
        for source in (
            'Completed a B.S. Pursuing an M.S.',
            'Completed a B.S. Currently pursuing an M.S.',
            "Bachelor of Science graduate, currently pursuing a Master's degree",
        ):
            with self.subTest(source=source):
                self.assertEqual(validate.claim_problems("Bachelor's degree holder", [source], set(), ()), [])
                self.assertTrue(validate.claim_problems("Master's degree holder", [source], set(), ()))
        self.assertTrue(validate.claim_problems("Master's degree holder", ['M.S., expected 2099'], set(), ()))
        self.assertTrue(validate.claim_problems("Master's degree holder", ['Pursuing an MBA, M.S. in Analytics'], set(), ()))

    def test_pending_degree_rejected_through_resume_and_answer_proposals(self):
        prof, _, _ = profile.save({'contact': {'name': 'Candidate'},
                                  'summary': "Pursuing a Master's degree in Computer Science",
                                  'education': [{'institution': 'Example', 'degree': 'M.S.', 'end': '2099'}]})
        job = jobs.add('Example', 'Engineer', 'Engineering')['id']
        jobs.set_requirements(job, [])
        claim = "Master's degree holder in Computer Science"
        for source in ('summary', prof['education'][0]['id']):
            with self.subTest(source=source), self.assertRaises(ResuError):
                package.propose_resume(job, {'summary': {'text': claim, 'sources': [source]}})
        package.add_question(job, 'Why do you want this role?', True, None, 'chars', None)
        with self.assertRaises(ResuError):
            package.propose_answers(job, [{'question_id': 'q1', 'text': claim, 'sources': ['summary']}])


class TermDetectionTests(IsolatedHome):
    def test_common_words_do_not_trigger(self):
        text = "We go to the rest area and react quickly; the spring term ended"
        self.assertEqual(find_terms(text), set())

    def test_symbols_and_aliases(self):
        found = find_terms("Shipped C++ and C# services on k8s with Postgres")
        self.assertTrue({"c++", "c#", "kubernetes", "postgresql"} <= found)

    def test_java_not_found_inside_javascript(self):
        self.assertNotIn("java", find_terms("Wrote JavaScript"))

    def test_hyphen_modifiers_preserve_technology_boundaries(self):
        found = find_terms('Kubernetes-based AWS-powered C++-based C#-based services')
        self.assertTrue({'kubernetes', 'amazon web services', 'c++', 'c#'} <= found)
        self.assertNotIn('c', found)
        self.assertNotIn('c', find_terms('Objective-C'))
