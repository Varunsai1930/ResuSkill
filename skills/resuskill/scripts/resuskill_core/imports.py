"""Reviewed, offline shortlist imports with bound previews and resumable writes."""
from __future__ import annotations

from copy import deepcopy
from urllib.parse import urlsplit, urlunsplit

from . import SCHEMA_VERSION, input_schema, jobs, listing, store
from .util import ResuError, content_hash, norm_text, now_iso, slugify

SPEC = {'company': str, 'title': str, 'description': str, 'source_url': str,
        'observed_at': str, 'source_namespace': str, 'requisition_id': str,
        'location': str, 'listing': dict}


def canonical_url(value):
    if not isinstance(value, str):
        raise ResuError('Posting URL must be text.')
    try:
        url = urlsplit(value.strip())
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            raise ValueError()
        port = url.port
        host = url.hostname.lower()
        if ':' in host:
            host = '[' + host + ']'
        if port and (url.scheme, port) not in (('http', 80), ('https', 443)):
            host += ':' + str(port)
        return urlunsplit((url.scheme.lower(), host, url.path or '/', url.query, ''))
    except ValueError:
        raise ResuError('Posting URL must be a valid HTTP(S) URL without credentials.') from None


def normalize(row):
    input_schema.check(row, SPEC, 'import record')
    for key in ('company', 'title', 'description', 'source_url', 'observed_at'):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ResuError('Import record requires nonempty ' + key)
    clean = {k: v.strip() if isinstance(v, str) else v for k, v in row.items()}
    clean['source_url'] = canonical_url(clean['source_url'])
    try:
        listing.timestamp(clean['observed_at'])
    except (TypeError, ValueError):
        raise ResuError('observed_at requires a timezone-aware ISO timestamp.') from None
    if bool(clean.get('requisition_id')) != bool(clean.get('source_namespace')):
        raise ResuError('Requisition identity requires both source_namespace and requisition_id.')
    clean['location'] = clean.get('location', '')
    clean['listing'] = listing.normalize(clean.get('listing', {}))
    return clean


def identity(row):
    if row.get('requisition_id'):
        return ['requisition', row['source_namespace'], row['requisition_id']]
    return ['url', row['source_url']]


def inventory():
    problems = []
    saved = jobs.list_jobs(problems)
    if problems:
        raise ResuError('Repair unreadable jobs before preparing or applying imports.', [f'{j}: {e}' for j, e in problems])
    result = {job['id']: content_hash(job) for job in saved}
    # Empty directories may be interrupted new-job writes; preserve them as explicit state.
    for folder in store.jobs_dir().iterdir():
        if folder.is_dir() and folder.name not in result:
            result[folder.name] = None
    return saved, result


def preview(data):
    if not isinstance(data, list) or not data:
        raise ResuError('Import input must be a nonempty JSON list.')
    saved, hashes = inventory()
    rows, seen = [], set()
    for index, raw in enumerate(data, 1):
        item = {'row': index, 'state': 'rejected', 'matches': []}
        try:
            clean = normalize(raw)
            key = content_hash(identity(clean))
            if key in seen:
                raise ResuError('Duplicate source identity within the input.')
            seen.add(key)
            matches = []
            for job in saved:
                recorded = job.get('import_source')
                if isinstance(recorded, dict) and recorded.get('identity') == identity(clean):
                    matches.append(job)
                elif not recorded and job.get('url'):
                    try:
                        if canonical_url(job['url']) == clean['source_url']:
                            matches.append(job)
                    except ResuError:
                        pass
            item['matches'] = [j['id'] for j in matches]
            if len(matches) == 1:
                old = matches[0]
                same = (all(old.get(k, '') == clean[k] for k in ('company', 'title', 'description', 'location'))
                        and old.get('listing', listing.DEFAULT) == clean['listing']
                        and old.get('url') == clean['source_url']
                        and (old.get('import_source') or {}).get('observed_at') == clean['observed_at'])
                item['state'] = 'duplicate' if same else 'update'
            elif len(matches) > 1:
                item['state'] = 'ambiguous'
            else:
                similar = [j['id'] for j in saved if norm_text(j['company']) == norm_text(clean['company']) and norm_text(j['title']) == norm_text(clean['title'])]
                item.update(state='possible_duplicate' if similar else 'addition', matches=similar)
            item['record'] = clean
        except ResuError as exc:
            item['error'] = str(exc)
        rows.append(item)
    return {'version': 1, 'input_hash': content_hash(data), 'existing_hashes': hashes, 'rows': rows}


def _job(clean, jid, old=None, at=None):
    now = at or now_iso()
    result = deepcopy(old) if old else {
        'id': jid, 'revision': 0, 'created_at': now, 'requirements': [], 'evidence': {}, 'overrides': {}, 'questions': [],
        'tracking': {'status': 'saved', 'history': [{'status': 'saved', 'at': now}], 'notes': []}}
    if old and old['description'] != clean['description']:
        result.update(requirements=[], evidence={}, overrides={})
        result.pop('requirements_reviewed_at', None)
    result.update({k: clean[k] for k in ('company', 'title', 'description', 'location')})
    result.update(url=clean['source_url'], listing=clean['listing'],
                  import_source={'identity': identity(clean), 'observed_at': clean['observed_at']},
                  schema_version=store.data_version(), revision=result['revision'] + 1, updated_at=now)
    jobs._check_stored(result, jid)
    return result


def apply(data, approved, selections, updates=None):
    updates = updates or {}
    if not isinstance(approved, dict) or approved.get('input_hash') != content_hash(data):
        raise ResuError('Input changed since preview; prepare and review a new preview.')
    if not selections or len(selections) != len(set(selections)):
        raise ResuError('Select each reviewed row exactly once with --select.')
    if set(updates) - set(selections):
        raise ResuError('Update selections must also be included in --select.')
    request = {'preview': approved, 'selections': selections, 'updates': updates}
    key = content_hash(request)
    journal_path = store.home() / 'imports' / (key + '.json')
    journal = store.read_json(journal_path)
    if journal is None:
        actual = preview(data)
        if actual != approved:
            raise ResuError('Stored jobs or preview changed; prepare and review a new preview.')
        saved, _ = inventory()
        by_id = {j['id']: j for j in saved}
        plan = []
        targets = set()
        for number in selections:
            item = next((r for r in actual['rows'] if r['row'] == number), None)
            if not item or item['state'] == 'rejected':
                raise ResuError('Selected row is missing or rejected; nothing imported.')
            target = updates.get(number)
            if target and target not in item['matches']:
                raise ResuError('Update target must be one of the reviewed matching jobs.')
            if item['state'] in ('update', 'ambiguous') and not target:
                raise ResuError('Updates and ambiguous matches require --update ROW=JOB.')
            if item['state'] == 'duplicate' and not target:
                continue
            # Selecting a possible duplicate without --update explicitly means keep both.
            jid = target or (slugify(item['record']['company'], 24) + '-' + slugify(item['record']['title'], 32) + '-' + key[:10] + '-' + str(number))
            if jid in targets or (not target and jid in actual['existing_hashes']):
                raise ResuError('Conflicting import destinations; nothing imported.')
            targets.add(jid)
            plan.append({'id': jid, 'row': number, 'before': actual['existing_hashes'].get(jid), 'original': by_id.get(target), 'after': _job(item['record'], jid, by_id.get(target))})
        journal = {'request_hash': key, 'before': actual['existing_hashes'], 'plan': plan, 'plan_hash': content_hash(plan), 'complete': False}
        store.write_json(journal_path, journal)
    if (not isinstance(journal, dict) or journal.get('request_hash') != key
            or not isinstance(journal.get('plan'), list) or not isinstance(journal.get('before'), dict)
            or any(not isinstance(k, str) or (v is not None and not isinstance(v, str)) for k, v in journal['before'].items())):
        raise ResuError('Import journal is damaged; restore a valid backup.')
    if journal.get('plan_hash') != content_hash(journal['plan']) or journal['before'] != approved.get('existing_hashes'):
        raise ResuError('Import recovery plan differs from its approved state.')
    journal_ids = set()
    expected_rows = {r['row'] for r in approved['rows'] if r['row'] in selections
                     and (r['state'] != 'duplicate' or updates.get(r['row']))}
    actual_rows = [s.get('row') for s in journal['plan'] if isinstance(s, dict)]
    if any(type(n) is not int for n in actual_rows) or len(actual_rows) != len(expected_rows) or set(actual_rows) != expected_rows:
        raise ResuError('Import recovery plan is incomplete or contains repeated rows.')
    for step in journal['plan']:
        if (not isinstance(step, dict) or not isinstance(step.get('id'), str)
                or not step['id'] or step['id'].startswith('.') or any(c in step['id'] for c in ('/', '\\', '\x00'))
                or step['id'] in journal_ids or not isinstance(step.get('after'), dict)
                or 'before' not in step or (step['before'] is not None and not isinstance(step['before'], str))):
            raise ResuError('Import journal step is damaged; restore a valid backup.')
        number = step.get('row')
        if type(number) is not int or number not in selections:
            raise ResuError('Import recovery row was not selected.')
        item = next((r for r in approved['rows'] if r['row'] == number), None)
        if item is None or item['state'] == 'rejected':
            raise ResuError('Import recovery row is invalid.')
        target = updates.get(number)
        expected_id = target or (slugify(item['record']['company'], 24) + '-' + slugify(item['record']['title'], 32) + '-' + key[:10] + '-' + str(number))
        original = step.get('original')
        before_hash = content_hash(original) if original is not None else None
        if step['id'] != expected_id or before_hash != step['before'] or step['before'] != approved['existing_hashes'].get(step['id']):
            raise ResuError('Import recovery destination differs from the preview.')
        expected_after = _job(item['record'], step['id'], original, step['after'].get('updated_at'))
        if expected_after != step['after']:
            raise ResuError('Import recovery content differs from the approved row.')
        journal_ids.add(step['id'])
    _, current = inventory()
    expected = dict(journal['before'])
    for step in journal['plan']:
        jobs._check_stored(step['after'], step['id'])
        actual_hash = current.get(step['id'])
        if actual_hash not in (step['before'], content_hash(step['after'])):
            raise ResuError('An import destination changed; refusing to overwrite it.')
        if step['id'] in current:
            expected[step['id']] = actual_hash
    if current != expected:
        raise ResuError('Saved jobs changed during the import; restore/review before retrying.')
    for step in journal['plan']:
        path = store.jobs_dir() / step['id'] / 'job.json'
        current_record = store.read_json(path)
        if current_record is not None and content_hash(current_record) == content_hash(step['after']):
            continue
        store.write_json(path, step['after'])
    journal['complete'] = True
    store.write_json(journal_path, journal)
    return {'complete': True, 'jobs': [p['id'] for p in journal['plan']], 'journal': str(journal_path)}
