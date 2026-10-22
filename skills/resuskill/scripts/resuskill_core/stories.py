"""Interview preparation kept separate from application approval."""
from __future__ import annotations

from html import escape
from pathlib import Path
import re
import shutil
import tempfile

from . import claims, input_schema, jobs, ledger, profile, store, validate
from .util import ResuError, now_iso

SPEC = {'situation': claims.SPEC, 'task': claims.SPEC, 'action': claims.SPEC,
        'result': (type(None), claims.SPEC), 'contribution_scope': str}


def normalize(data):
    input_schema.check(data, SPEC, 'interview story')
    if any(not isinstance(data.get(k), dict) for k in ('situation', 'task', 'action')) or 'result' not in data:
        raise ResuError('A story needs sourced situation, task, action and an explicit result (null if unknown).')
    if data.get('contribution_scope') not in ('personal', 'team', 'shared'):
        raise ResuError('Specify contribution_scope as personal, team or shared; describe your own part in action.')
    for part in parts(data):
        claims.shape(part)
    return dict(data)


def parts(content):
    return [content[k] for k in ('situation', 'task', 'action', 'result') if content[k] is not None]


def shape(record):
    if not isinstance(record, dict) or not isinstance(record.get('references'), dict) or not isinstance(record.get('fingerprint'), str):
        raise ResuError('Stored story is damaged; restore a valid backup.')
    normalize(record.get('content'))


def build(data):
    content = normalize(data)
    refs = claims.review(parts(content), profile.load())
    return {'content': content, 'references': refs, 'fingerprint': claims.fingerprint(content, refs), 'created_at': now_iso()}


def errors(record):
    try:
        shape(record)
        current = build(record['content'])
        if current['fingerprint'] != record['fingerprint'] or current['references'] != record['references']:
            return ['Story content or sources changed; propose and review again.']
        return []
    except ResuError as exc:
        return [str(exc), *exc.details]


def load():
    ledger.require_v2()
    data = store.read_json(store.home() / 'stories.json', {'version': 1, 'records': []})
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1 or not isinstance(data.get('records'), list):
        raise ResuError('Stored story library is damaged; restore a valid backup.')
    seen = set()
    for row in data['records']:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not re.fullmatch(r'st[1-9]\d*', row['id']) or row['id'] in seen:
            raise ResuError('Stored story ID is missing, repeated or invalid.')
        if row.get('proposal') is None and row.get('accepted') is None:
            raise ResuError('Stored story has neither a proposal nor accepted content.')
        for key in ('proposal', 'accepted'):
            if row.get(key) is not None:
                shape(row[key])
        seen.add(row['id'])
    return data


def save(data):
    store.write_json(store.home() / 'stories.json', data)


def find(data, ident):
    row = next((r for r in data['records'] if r['id'] == ident), None)
    if row is None:
        raise ResuError('Unknown story ID: ' + ident)
    return row


def propose(data, ident=None):
    library = load()
    record = build(data)
    if ident:
        row = find(library, ident)
    else:
        ident = 'st' + str(max((int(r['id'][2:]) for r in library['records']), default=0) + 1)
        row = {'id': ident, 'accepted': None, 'proposal': None}
        library['records'].append(row)
    row['proposal'] = record
    save(library)
    return row


def accept(ident):
    library = load()
    row = find(library, ident)
    record = row.get('proposal')
    if record is None:
        raise ResuError('No pending story to accept.')
    problems = errors(record)
    if problems:
        raise ResuError('Story needs renewed review.', problems)
    row['accepted'], row['proposal'] = record, None
    save(library)
    return row


def questions(record):
    result = []
    for ident, ref in record['references'].items():
        if ref.get('kind') != 'project_evidence':
            continue
        ev = ref['citation']
        result.append({'source': ident, 'commit': ev['commit'], 'path': ev['path'],
                       'start_line': ev['start_line'], 'end_line': ev['end_line'], 'excerpt': ev['excerpt'],
                       'question': 'Explain how this excerpt works, the tradeoffs you considered, and which part you personally implemented.'})
    return result


def show(ident, proposal=False):
    row = find(load(), ident)
    record = row.get('proposal' if proposal else 'accepted')
    if record is None:
        return {'id': ident, 'state': 'unavailable', 'record': None, 'errors': []}
    problems = errors(record)
    return {'id': ident, 'state': 'stale' if problems else ('proposed' if proposal else 'accepted'),
            'record': record, 'errors': problems, 'implementation_questions': [] if problems else questions(record)}


def check(ident=None):
    library = load()
    selected = [find(library, ident)] if ident else library['records']
    return [show(r['id'], proposal=r.get('accepted') is None) for r in selected]


def suggest(job_id):
    job = jobs.load(job_id)
    if not job.get('requirements') and not job.get('requirements_reviewed_at'):
        raise ResuError('Review the saved job requirements before requesting story suggestions.')
    prof = profile.load()
    confirmed = {validate.canon(s['name']) for s in prof['skills']}
    result = []
    for item in check():
        if item['state'] != 'accepted':
            continue
        record = item['record']
        technologies = set()
        for ref in record['references'].values():
            technologies.update(validate.canon(t) for t in ref.get('technologies', []))
            if ref.get('kind') == 'project_evidence':
                project_id = ref['citation']['project_id']
                entry = next((p for p in prof['projects'] if p['id'] == project_id), None)
                technologies.update(validate.canon(t) for t in (entry or {}).get('technologies', []))
        skills = technologies & confirmed
        basis = []
        for req in job.get('requirements', []):
            wanted = {validate.canon(s) for s in (req.get('criterion') or {}).get('skills', [])}
            matches = sorted(wanted & skills)
            if matches:
                basis.append({'requirement': req['id'], 'text': req['text'], 'skills': matches})
        if basis:
            result.append({'id': item['id'], 'matched_requirements': len(basis), 'basis': basis})
    return sorted(result, key=lambda r: (-r['matched_requirements'], r['id']))


def export(ident, output):
    item = show(ident)
    if item['state'] != 'accepted':
        raise ResuError('Only a current accepted story can be exported.', item['errors'])
    target = Path(output).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise ResuError('Choose a new story export directory.')
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.story-', dir=target.parent))
    try:
        store.write_json(staging / 'story.json', item)
        content = item['record']['content']
        body = '<h1>Interview story ' + escape(ident) + '</h1><p>Contribution: ' + escape(content['contribution_scope']) + '</p>'
        for key in ('situation', 'task', 'action', 'result'):
            part = content[key]
            body += '<h2>' + key.title() + '</h2><p>' + escape(part['text'] if part else 'Result unknown; no metric claimed.') + '</p>'
        import json
        body += '<h2>Source review and implementation questions</h2><pre>' + escape(json.dumps(item, indent=2, ensure_ascii=False)) + '</pre>'
        html = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Interview story</title><style>body{font:16px/1.6 sans-serif;max-width:800px;margin:40px auto;padding:20px}p,pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>' + body + '</html>'
        (staging / 'story.html').write_text(html, encoding='utf-8')
        if show(ident) != item:
            raise ResuError('Story changed during export; retry after review.')
        if target.exists() or target.is_symlink():
            raise ResuError('Story destination appeared during export.')
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {'output': str(target), 'html': str(target / 'story.html'), 'json': str(target / 'story.json')}
