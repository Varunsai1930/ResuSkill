from pathlib import Path

from helpers import IsolatedHome, fixture
from resuskill_core import jobs, package, profile, render, store


class ClaimReviewTests(IsolatedHome):
    def setUp(self):
        super().setUp()
        self.job = self.seed()
        package.propose_resume(self.job, fixture('proposal_good.json'))

    def page(self):
        return render.review_html(jobs.load(self.job), profile.load(), package.load(self.job),
                                  package.load_proposal(self.job))

    def test_sources_and_changes_are_visible_without_mutating_state(self):
        before = {str(p): p.read_bytes() for p in Path(self._tmp).rglob('*.json')}
        html = self.page()
        self.assertIn('exp-1-b1', html)
        self.assertIn('Sample Analytics', html)
        self.assertIn('Current rule checks passed', html)
        self.assertIn('Meaning, attribution and real-world accuracy are not checked automatically', html)
        self.assertIn('<ins>', html)
        self.assertIn('<del>', html)
        self.assertEqual(before, {str(p): p.read_bytes() for p in Path(self._tmp).rglob('*.json')})

    def test_current_source_failure_is_not_displayed_as_passing(self):
        data = profile.load()
        data['experience'][0]['bullets'][0]['text'] = 'Built reporting tools for 500 users'
        profile.save(data)
        html = self.page()
        self.assertIn('Checks need attention', html)
        self.assertIn('numbers/years not in its sources', html)
        self.assertNotIn('Current rule checks passed', html)

    def test_missing_source_remains_visible(self):
        data = profile.load()
        data['experience'][0]['bullets'] = data['experience'][0]['bullets'][1:]
        profile.save(data)
        html = self.page()
        self.assertIn('exp-1-b1 — missing from current profile', html)
        self.assertNotIn('Current rule checks passed', html)

    def test_accepted_and_replacement_answers_checked_separately(self):
        package.add_question(self.job, 'Why are you interested in this role?', True, None, 'chars', None)
        package.propose_answers(self.job, [{'question_id': 'q1', 'text': 'Built a Flask API for 1,200 users', 'sources': ['exp-1-b1']}])
        package.accept_answers(self.job, [])
        package.propose_answers(self.job, [{'question_id': 'q1', 'text': 'Built Python tools', 'sources': ['exp-1-b1']}])
        data = profile.load()
        data['experience'][0]['bullets'][0]['text'] = 'Built Python tools'
        profile.save(data)
        html = self.page().split('<h2>Answers</h2>')[1]
        self.assertIn('Replacement draft (pending review)', html)
        self.assertIn('Checks need attention', html)
        self.assertIn('Current rule checks passed', html)

    def test_user_answer_is_not_given_ai_validation_badge(self):
        package.add_question(self.job, 'What are your salary expectations?', True, None, 'chars', None)
        package.set_answer(self.job, 'q1', '$100,000 <script>alert(1)</script>')
        html = self.page().split('<h2>Answers</h2>')[1]
        self.assertNotIn('Current rule checks passed', html)
        self.assertIn('Not an AI claim check', html)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_word_diff_escapes_both_sides(self):
        html = render._word_changes('<script>old</script>', '<img src=x onerror=bad>')
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('&lt;img', html)

    def test_exact_source_is_shown_as_unchanged(self):
        draft = fixture('proposal_good.json')
        draft['experience'][0]['bullets'][0]['text'] = profile.load()['experience'][0]['bullets'][0]['text']
        package.propose_resume(self.job, draft)
        self.assertIn('Unchanged wording', self.page())
