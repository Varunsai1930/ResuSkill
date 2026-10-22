"""Optional cover letters: pending writing is separate from the accepted package."""
from __future__ import annotations

from html import escape
from pathlib import Path
import shutil
import tempfile

from . import claims, input_schema, jobs, ledger, package, profile, render, store
from .util import ResuError, now_iso

OPENINGS = {'application': 'Please consider my application for this role.', 'interest': 'I would welcome the opportunity to discuss this role.'}
CLOSINGS = {'thanks': 'Thank you for considering my application.', 'discussion': 'I look forward to discussing how I could contribute.'}
SPEC = {'paragraphs': [claims.SPEC], 'opening': str, 'closing': str}


def normalize(data):
    input_schema.check(data, SPEC, 'letter')
    if not data.get('paragraphs'):
        raise ResuError('A letter needs at least one sourced factual paragraph.')
    for paragraph in data['paragraphs']:
        claims.shape(paragraph)
    clean = dict(data, opening=data.get('opening', 'application'), closing=data.get('closing', 'thanks'))
    if clean['opening'] not in OPENINGS or clean['closing'] not in CLOSINGS:
        raise ResuError('Choose a documented nonfactual opening and closing.')
    return clean


def shape(record):
    if not isinstance(record, dict) or not isinstance(record.get('content'), dict) or not isinstance(record.get('fingerprint'), str) or not isinstance(record.get('references'), dict):
        raise ResuError('Stored letter is damaged; restore a valid backup.')
    if normalize(record['content']) != record['content']:
        raise ResuError('Stored letter is incomplete; restore a valid backup.')


def build(data, job, prof):
    clean = normalize(data)
    refs = claims.review(clean['paragraphs'], prof, job)
    context = {'company': job['company'], 'title': job['title']}
    return {'content': clean, 'references': refs, 'context': context,
            'fingerprint': claims.fingerprint(clean, refs, context), 'created_at': now_iso()}


def check(record, job, prof):
    try:
        shape(record)
        current = build(record['content'], job, prof)
        if current['fingerprint'] != record['fingerprint'] or record.get('references') != current['references'] or record.get('context') != current['context']:
            return ['Letter sources or employer/role changed; propose and review it again.']
        return []
    except ResuError as exc:
        return [str(exc), *exc.details]


def propose(job_id, data):
    ledger.require_v2()
    record = build(data, jobs.load(job_id), profile.load())
    pkg = package.load(job_id)
    pkg['letter_proposal'] = record
    package.save(job_id, pkg, content_changed=False)
    return record


def accept(job_id):
    ledger.require_v2()
    pkg = package.load(job_id)
    record = pkg.get('letter_proposal')
    if record is None:
        raise ResuError('No pending letter to accept.')
    errors = check(record, jobs.load(job_id), profile.load())
    if errors:
        raise ResuError('Letter needs a new review.', errors)
    pkg['letter'] = record
    pkg['letter_proposal'] = None
    package.save(job_id, pkg, content_changed=False)
    return record


def remove(job_id, proposal=False):
    ledger.require_v2()
    pkg = package.load(job_id)
    pkg['letter_proposal' if proposal else 'letter'] = None
    package.save(job_id, pkg, content_changed=False)


def html(record, job, prof, source_review=False):
    content = record['content']
    paragraphs = [OPENINGS[content['opening']]] + [p['text'] for p in content['paragraphs']] + [CLOSINGS[content['closing']]]
    body = ''.join('<p>' + escape(p) + '</p>' for p in paragraphs)
    if source_review:
        body += '<h2>Source review</h2><p>Source checks do not establish semantic truth. Confirm personal contribution and outcomes.</p>'
        import json
        body += '<pre>' + escape(json.dumps(record['references'], indent=2, ensure_ascii=False)) + '</pre>'
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Cover letter</title>'
            '<style>body{font:12pt/1.6 sans-serif;max-width:760px;margin:40px auto;padding:24px}p,pre{overflow-wrap:anywhere}pre{white-space:pre-wrap}@media print{body{margin:0}}</style>'
            '<h1>' + escape(prof['contact']['name']) + '</h1><h2>' + escape(job['title']) + ' — ' + escape(job['company']) + '</h2>' + body + '</html>')


def export(job_id, output, pdf=False):
    ledger.require_v2()
    pkg, job, prof = package.load(job_id), jobs.load(job_id), profile.load()
    record = pkg.get('letter')
    if record is None:
        raise ResuError('No accepted letter selected.')
    errors = check(record, job, prof)
    if errors:
        raise ResuError('Accepted letter cannot be exported.', errors)
    target = Path(output).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise ResuError('Choose a new export directory; existing files will not be replaced.')
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix='.letter-', dir=target.parent))
    try:
        (staged / 'letter.html').write_text(html(record, job, prof), encoding='utf-8')
        (staged / 'sources.html').write_text(html(record, job, prof, True), encoding='utf-8')
        if pdf:
            render.print_pdf(staged / 'letter.html', staged / 'letter.pdf')
        # Sources may have changed while the browser was running.
        if check(record, jobs.load(job_id), profile.load()):
            raise ResuError('Letter sources changed during export; retry after review.')
        if target.exists() or target.is_symlink():
            raise ResuError('Export destination appeared during preparation.')
        staged.rename(target)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return {'output': str(target), 'html': str(target / 'letter.html'), 'pdf': str(target / 'letter.pdf') if pdf else None}


def review_section(pkg, job, prof):
    import json
    parts = []
    for key, label in (('letter', 'Accepted cover letter'), ('letter_proposal', 'Pending cover letter (not selected)')):
        record = pkg.get(key)
        if record is None:
            continue
        errors = check(record, job, prof)
        parts.append('<h2>' + label + '</h2><p>' + escape('; '.join(errors) if errors else 'Source checks passed; human review required for meaning and contribution.') + '</p>')
        parts.extend('<p class="claim-text">' + escape(p['text']) + '</p>' for p in record['content']['paragraphs'])
        parts.append('<details><summary>Cited sources</summary><pre class="claim-text">' + escape(json.dumps(record['references'], ensure_ascii=False, indent=2)) + '</pre></details>')
    return ''.join(parts)
