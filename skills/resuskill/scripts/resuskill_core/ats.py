"""Offline resume preflight. Keyword presence is not proof of eligibility or ATS success."""
from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

from . import jobs, package, profile, render, store, style, validate
from .skills import canon, display, find_terms
from .util import ResuError

LIMITATION = ('Local heuristics only: no employer ATS was queried. Keyword presence does not prove '
              'competence, eligibility, semantic support, or a hiring outcome. PDF extraction '
              'does not verify visual layout or every parser\'s reading order.')


class VisibleText(HTMLParser):
    """Read visible source text, excluding style, scripts and the contact header."""
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []
        self.headings = []
        self.heading = False
        self.risky_tags = set()

    def handle_starttag(self, tag, attrs):
        if tag in ('style', 'script', 'header'):
            self.hidden += 1
        if tag == 'h2':
            self.heading = True
        if tag in ('table', 'img', 'svg', 'canvas', 'iframe'):
            self.risky_tags.add(tag)

    def handle_endtag(self, tag):
        if tag in ('style', 'script', 'header'):
            self.hidden = max(0, self.hidden - 1)
        if tag == 'h2':
            self.heading = False

    def handle_data(self, text):
        if not self.hidden and text.strip():
            self.parts.append(text.strip())
            if self.heading:
                self.headings.append(text.strip())


def _flat(text):
    # Preserve decimal points, signs and email separators. Deleting punctuation
    # can make different claims (35% and 3.5%) compare equal.
    normalized = unicodedata.normalize('NFKC', text).casefold().translate(str.maketrans({
        '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2013': '-', '\u2014': '-', '\u2212': '-',
        '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"',
    }))
    return re.sub(r'\s+', ' ', normalized).strip()


def _retained(value, text):
    # Avoid accepting a contact number as the prefix of a different number.
    value = _flat(value)
    return bool(value and re.search(r'(?<!\w)' + re.escape(value) + r'(?!\w)', text))


def extract_pdf(path):
    """Optional local parser; no OCR, network requests, or dependency installation."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise ResuError('PDF must be an existing file')
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ResuError('PDF check is limited to 20 MiB')
    with path.open('rb') as stream:
        if stream.read(5) != b'%PDF-':
            raise ResuError('Selected file does not have a PDF header')
    tool = shutil.which('pdftotext')
    if tool:
        try:
            run = subprocess.run([tool, '-enc', 'UTF-8', '-layout', str(path.resolve()), '-'],
                                 capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            raise ResuError('Local PDF text extraction failed or timed out')
        if run.returncode:
            raise ResuError('Local PDF parser could not read this file; check encryption or corruption')
        return run.stdout.decode('utf-8', errors='replace'), 'pdftotext'
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, None
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ResuError('Encrypted PDFs are not supported by this check')
        if len(reader.pages) > 30:
            raise ResuError('PDF check is limited to 30 pages')
        return '\n'.join(page.extract_text() or '' for page in reader.pages), 'pypdf'
    except ResuError:
        raise
    except Exception:
        raise ResuError('Local PDF parser could not read this file; check encryption or corruption')


def check(job_id, use_proposal=False, pdf=None):
    job = jobs.load(job_id)
    prof = profile.load()
    if use_proposal:
        record = package.load_proposal(job_id)
        if record is not None and not isinstance(record, dict):
            raise ResuError('Stored proposal is damaged; restore it or propose a new draft')
        resume = (record or {}).get('proposal')
    else:
        resume = package.load(job_id).get('resume')
    if not resume:
        raise ResuError('No selected resume. Use --proposal for a pending draft, or accept a reviewed proposal first')
    # Revalidate against current sources; stale drafts must not gain a reassuring report.
    resume, validation_warnings = validate.validate_proposal(prof, job, resume)
    settings = style.saved(store.job_dir(job_id) / 'out')
    parsed = VisibleText()
    parsed.feed(render.resume_body(prof, resume, settings))
    body = '\n'.join(parsed.parts)
    extra = validate.detection_terms(prof, job)
    present = find_terms(body, extra)
    confirmed = profile.skill_keys(prof)
    absent = {canon(t) for t in prof.get('skills_absent') or []}
    sources = profile.sources(prof)
    issues = []

    def issue(code, message, severity='warning'):
        issues.append({'code': code, 'severity': severity, 'message': message})

    groups = []
    targets = set()
    for req in job.get('requirements') or []:
        crit = req.get('criterion') or {}
        if crit.get('type') != 'skill':
            continue
        terms = list(dict.fromkeys(canon(t) for t in crit['skills']))
        targets.update(terms)
        matches = [t for t in terms if t in present]
        covered = bool(matches) if crit['match'] == 'any' else len(matches) == len(terms)
        gaps = []
        # Do not suggest every unmentioned alternative once an OR group is covered.
        for term in ([] if covered else [t for t in terms if t not in present]):
            support = [sid for sid, src in sources.items()
                       if term in {canon(t) for t in src.get('technologies') or []}
                       or (sid.startswith('skill:') and canon(sid[6:]) == term)]
            state = 'confirmed_absent' if term in absent else ('supported_omitted' if term in confirmed else 'not_confirmed')
            gaps.append({'term': display(term), 'state': state, 'sources': support,
                         'action': ('Consider including the confirmed skill if relevant; do not invent experience.'
                                    if state == 'supported_omitted' else 'Do not add without user-confirmed facts.')})
        groups.append({'requirement': req['id'], 'text': req['text'], 'importance': req['importance'],
                       'match': crit['match'], 'terms': [display(t) for t in terms],
                       'present': [display(t) for t in matches], 'keyword_covered': covered,
                       'gaps': gaps})
    if not groups:
        issue('no_skill_criteria', 'No structured skill criteria are saved; review the job requirements before judging coverage.')
    # Other job mentions are only context, never auto-promoted to required skills.
    contextual = sorted(find_terms(job['description'], extra) - targets)
    if not job.get('requirements_reviewed_at'):
        issue('requirements_unreviewed', 'The extracted requirements have not been recorded as reviewed.')
    for field in ('name', 'email', 'phone'):
        if not prof['contact'].get(field):
            issue('contact_missing', f'Contact {field} is missing; confirm it with the user before adding.')
    if not resume.get('education') and any(r['category'] == 'education' for r in job.get('requirements') or []):
        issue('education_omitted', 'The job has education requirements, but education is omitted from this resume.')
    for tag in sorted(parsed.risky_tags):
        issue('complex_markup', f'Rendered resume contains {tag}; review its text extraction and reading order.')
    for section in ('experience', 'projects'):
        for item in resume.get(section) or []:
            entry = profile.entry_by_id(prof, item['entry'])[1]
            if section == 'experience' and not (entry.get('start') and entry.get('end')):
                issue('experience_dates_missing', f"{item['entry']}: employment dates are incomplete; confirm them instead of guessing.")
    for message in validation_warnings:
        issue('content_review', message)
    pdf_result = {'status': 'not_checked', 'reason': 'Pass --pdf FILE to inspect the actual exported PDF.'}
    if pdf is not None:
        text, parser = extract_pdf(pdf)
        if text is None:
            pdf_result = {'status': 'not_checked', 'reason': 'Install Poppler (pdftotext) or optional pypdf to enable local PDF extraction.'}
            issue('pdf_not_checked', pdf_result['reason'])
        else:
            flattened = _flat(text)
            expected = [('contact.' + key, value) for key, value in prof['contact'].items()
                        if key in ('name', 'email', 'phone') and value]
            expected += [('heading', t) for t in parsed.headings]
            if resume.get('summary'):
                expected.append(('summary', resume['summary']['text']))
            for section in ('experience', 'projects'):
                for item in resume.get(section) or []:
                    entry = profile.entry_by_id(prof, item['entry'])[1]
                    for key in (('title', 'organization') if section == 'experience' else ('name',)):
                        if entry.get(key):
                            expected.append((item['entry'] + '.' + key, entry[key]))
                    if render.date_range(entry):
                        expected.append((item['entry'] + '.dates', render.date_range(entry)))
                    expected += [(f"{item['entry']}.bullet.{n}", b['text']) for n, b in enumerate(item['bullets'], 1)]
            for edu_id in resume['education']:
                entry = profile.entry_by_id(prof, edu_id)[1]
                expected += [(edu_id + '.' + key, entry[key]) for key in ('institution', 'degree', 'field') if entry.get(key)]
                if render.date_range(entry):
                    expected.append((edu_id + '.dates', render.date_range(entry)))
            for cert_id in resume['certifications']:
                cert = next(c for c in prof['certifications'] if c['id'] == cert_id)
                expected.append((cert_id, cert['name']))
            missing = [{'item': key, 'text': value} for key, value in expected if not _retained(value, flattened)]
            pdf_terms = find_terms(text, extra)
            missing_skills = sorted(find_terms(', '.join(resume['skills']), extra) - pdf_terms)
            pdf_result = {'status': 'review_needed' if missing or missing_skills or not flattened else 'text_checks_passed',
                          'parser': parser, 'checked_blocks': len(expected), 'missing_blocks': missing,
                          'missing_skills': [display(t) for t in missing_skills]}
            if not flattened:
                issue('pdf_no_text', 'No readable text was extracted. Export a text PDF, rather than an image-only resume.', 'error')
            elif missing or missing_skills:
                issue('pdf_content_mismatch', 'The PDF does not retain all checked content from the selected resume. Check for a stale export, clipping or extraction errors.', 'error')
    summary = {level: {'covered': sum(g['keyword_covered'] for g in groups if g['importance'] == level),
                       'total': sum(g['importance'] == level for g in groups)}
               for level in ('required', 'preferred', 'unspecified')}
    return {'job': job_id, 'mode': 'proposal' if use_proposal else 'accepted',
            'profile_revision': prof['_meta']['revision'], 'job_revision': job['revision'],
            'limitation': LIMITATION, 'keyword_groups': groups, 'coverage': summary,
            'contextual_mentions': [display(t) for t in contextual],
            'non_skill_note': 'Degree, location, experience and soft-skill eligibility are assessed separately by the checklist; keyword presence is not a Met judgment.',
            'context_note': 'Unclassified mentions may be examples, negated skills or company boilerplate; review their context.',
            'issues': issues, 'pdf': pdf_result,
            'resume_text': prof['contact']['name'] + '\n' + body}


def text_report(result):
    lines = ['ATS preflight — ' + result['mode'], result['limitation'], '']
    for level, counts in result['coverage'].items():
        lines.append(f"{level.title()} skill groups present: {counts['covered']}/{counts['total']}")
    for group in result['keyword_groups']:
        lines.append(f"{'PRESENT' if group['keyword_covered'] else 'GAP'}: {group['text']} ({group['match']} of {', '.join(group['terms'])})")
        lines.extend(f"  {g['term']}: {g['state']}. {g['action']}" for g in group['gaps'])
    if result['contextual_mentions']:
        lines += ['', 'Other job mentions (context only): ' + ', '.join(result['contextual_mentions']), result['context_note']]
    lines += ['', result['non_skill_note'], 'PDF: ' + result['pdf']['status']]
    if result['pdf'].get('reason'):
        lines.append(result['pdf']['reason'])
    lines.extend('  Missing PDF block: ' + item['item'] for item in result['pdf'].get('missing_blocks', []))
    if result['pdf'].get('missing_skills'):
        lines.append('  Missing PDF skills: ' + ', '.join(result['pdf']['missing_skills']))
    lines.extend(f"{i['severity'].upper()}: {i['message']}" for i in result['issues'])
    return '\n'.join(lines)
