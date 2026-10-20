import io
import json
import subprocess
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from helpers import IsolatedHome, fixture
from resuskill_core import ats, jobs, package, profile, render, store
from resuskill_core.cli import main
from resuskill_core.util import ResuError


class AtsTests(IsolatedHome):
    def ready(self):
        job = self.seed()
        package.propose_resume(job, fixture('proposal_good.json'))
        return job

    def extracted(self, job):
        prof = profile.load()
        resume = package.load_proposal(job)['proposal']
        body = ats.VisibleText()
        body.feed(render.resume_body(prof, resume))
        return ' '.join(str(prof['contact'][key]) for key in ('name', 'email', 'phone')) + '\n' + '\n'.join(body.parts)

    def test_all_and_any_groups_do_not_reward_unmatched_alternatives(self):
        job = self.ready()
        reqs = fixture('requirements.json')
        reqs[4]['criterion']['skills'] = ['Python', 'Kafka']
        jobs.set_requirements(job, reqs)
        result = ats.check(job, True)
        self.assertEqual(result['coverage']['required'], {'covered': 1, 'total': 1})
        group = result['keyword_groups'][1]
        self.assertTrue(group['keyword_covered'])
        self.assertEqual(group['gaps'], [])
        self.assertFalse(result['keyword_groups'][2]['keyword_covered'])
        self.assertEqual(result['keyword_groups'][2]['gaps'][0]['state'], 'confirmed_absent')
        self.assertNotIn('score', result)

    def test_supported_omissions_have_sources_but_unconfirmed_skills_are_not_recommended(self):
        job = self.ready()
        prof = profile.load()
        prof['skills'].append({'name': 'Kafka', 'category': 'Data'})
        profile.save(prof)
        result = ats.check(job, True)
        gap = next(g for g in result['keyword_groups'] if g['requirement'] == 'r5')['gaps']
        kafka = next(g for g in gap if g['term'] == 'Kafka')
        java = next(g for g in gap if g['term'] == 'Java')
        self.assertEqual(kafka['state'], 'supported_omitted')
        self.assertIn('skill:kafka', kafka['sources'])
        self.assertEqual(java['state'], 'not_confirmed')
        self.assertEqual(java['sources'], [])

    def test_skill_matches_use_visible_resume_not_hrefs_or_source_ids(self):
        job = self.ready()
        prof = profile.load()
        prof['contact']['links']['java'] = 'https://example.test/Java'
        profile.save(prof)
        result = ats.check(job, True)
        group = next(g for g in result['keyword_groups'] if g['requirement'] == 'r5')
        self.assertFalse(group['keyword_covered'])
        # C++ must not also match C, and JavaScript must not also match Java.
        self.assertEqual(ats.find_terms('C++ JavaScript'), {'c++', 'javascript'})
        self.assertNotIn('go', ats.find_terms('go to work'))

    def test_accepted_and_proposal_are_explicit_and_current_claims_revalidate(self):
        job = self.ready()
        with self.assertRaises(ResuError):
            ats.check(job)
        package.accept_resume(job)
        self.assertEqual(ats.check(job)['mode'], 'accepted')
        prof = profile.load()
        prof['experience'][0]['bullets'][0]['text'] = 'Built a Flask service'
        profile.save(prof)
        with self.assertRaises(ResuError):
            ats.check(job, True)

    def test_unreviewed_and_empty_criteria_have_no_percent_or_success_score(self):
        job = self.seed(with_requirements=False)
        package.propose_resume(job, fixture('proposal_good.json'))
        result = ats.check(job, True)
        self.assertEqual(result['coverage']['required']['total'], 0)
        self.assertIn('no_skill_criteria', [i['code'] for i in result['issues']])
        self.assertIn('requirements_unreviewed', [i['code'] for i in result['issues']])
        self.assertEqual(result['pdf']['status'], 'not_checked')

    def test_actual_pdf_text_retains_content_aliases_and_typography(self):
        job = self.ready()
        text = self.extracted(job).replace('Jordan Example', 'JORDAN EXAMPLE').replace('\n', ' \n\t')
        self.assertEqual(ats.find_terms('postgres'), {'postgresql'})
        with patch.object(ats, 'extract_pdf', return_value=(text, 'test-parser')):
            report = ats.check(job, True, 'sample.pdf')
        self.assertEqual(report['pdf']['status'], 'text_checks_passed')
        self.assertEqual(report['pdf']['missing_blocks'], [])
        self.assertEqual(report['pdf']['missing_skills'], [])

    def test_wrong_or_image_pdf_fails_even_when_html_has_all_keywords(self):
        job = self.ready()
        for text, code in [('', 'pdf_no_text'), ('Python SQL Resume', 'pdf_content_mismatch')]:
            with self.subTest(text=text), patch.object(ats, 'extract_pdf', return_value=(text, 'test-parser')):
                result = ats.check(job, True, 'sample.pdf')
            self.assertIn(code, [i['code'] for i in result['issues']])
            self.assertEqual(result['pdf']['status'], 'review_needed')

    def test_missing_optional_parser_does_not_claim_pdf_passed(self):
        job = self.ready()
        with patch.object(ats, 'extract_pdf', return_value=(None, None)):
            result = ats.check(job, True, 'sample.pdf')
        self.assertEqual(result['pdf']['status'], 'not_checked')
        self.assertIn('pdf_not_checked', [i['code'] for i in result['issues']])

    def test_cli_error_status_and_json_are_read_only(self):
        job = self.ready()
        before = {p.relative_to(self._tmp): p.read_bytes() for p in Path(self._tmp).rglob('*') if p.is_file()}
        output = io.StringIO()
        with patch.object(ats, 'extract_pdf', return_value=('', 'test-parser')), redirect_stdout(output):
            code = main(['ats', job, '--proposal', '--pdf', 'sample.pdf', '--json'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())['pdf']['status'], 'review_needed')
        after = {p.relative_to(self._tmp): p.read_bytes() for p in Path(self._tmp).rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_pdf_input_and_local_parser_failures(self):
        path = Path(self._tmp) / 'file.pdf'
        path.write_text('not a PDF')
        with self.assertRaises(ResuError):
            ats.extract_pdf(path)
        path.write_bytes(b'%PDF-1.7\n')
        with patch.object(ats.shutil, 'which', return_value='/bin/pdftotext'), patch.object(ats.subprocess, 'run', side_effect=subprocess.TimeoutExpired('pdftotext', 20)):
            with self.assertRaisesRegex(ResuError, 'timed out'):
                ats.extract_pdf(path)
        with patch.object(ats.shutil, 'which', return_value='/bin/pdftotext'), patch.object(ats.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, b'', b'private content')):
            with self.assertRaises(ResuError) as error:
                ats.extract_pdf(path)
            self.assertNotIn('private content', str(error.exception))

    def test_contact_and_education_omissions_are_actionable(self):
        job = self.ready()
        prof = profile.load()
        prof['contact']['phone'] = ''
        profile.save(prof)
        draft = fixture('proposal_good.json')
        draft['education'] = []
        package.propose_resume(job, draft)
        result = ats.check(job, True)
        codes = [i['code'] for i in result['issues']]
        self.assertIn('contact_missing', codes)
        self.assertIn('education_omitted', codes)

    def test_clipped_bullet_is_flagged_despite_matching_keyword_list(self):
        job = self.ready()
        text = self.extracted(job).replace('Cut report generation time 35% with targeted PostgreSQL indexes', '')
        with patch.object(ats, 'extract_pdf', return_value=(text, 'test-parser')):
            result = ats.check(job, True, 'sample.pdf')
        self.assertEqual(result['pdf']['missing_skills'], [])
        self.assertTrue(any(b['item'] == 'exp-1.bullet.2' for b in result['pdf']['missing_blocks']))
        self.assertIn('pdf_content_mismatch', [i['code'] for i in result['issues']])

    def test_pdf_comparison_preserves_numbers_signs_and_email_separators(self):
        job = self.ready()
        text = self.extracted(job)
        for old, new in [('35%', '3.5%'), ('35%', '-35%'),
                         ('1,200', '12.00'), ('jordan@example.com', 'jordanexample.com'),
                         ('+1 555 0100', '+1 555 01000')]:
            with self.subTest(change=(old, new)), patch.object(ats, 'extract_pdf', return_value=(text.replace(old, new), 'test-parser')):
                result = ats.check(job, True, 'sample.pdf')
                self.assertEqual(result['pdf']['status'], 'review_needed')
                self.assertIn('pdf_content_mismatch', [i['code'] for i in result['issues']])
