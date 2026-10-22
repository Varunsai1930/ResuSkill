"""Pinned local Git evidence with separate, explicit user attestations."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
import os
import subprocess

from . import input_schema, profile, store
from .util import ResuError, content_hash, now_iso

SPEC = {k: str for k in ('repository', 'commit', 'path', 'excerpt', 'observed_fact', 'project_id', 'bullet_id', 'contribution', 'outcome')}
SPEC.update(start_line=int, end_line=int)


def require_v2():
    if store.data_version() != 2:
        raise ResuError('Run migrate --output NEW_DIR and use the migrated data directory before using evidence or derivative artifacts.')


def _git(repo, *args):
    try:
        result = subprocess.run(['git', '-C', str(repo), *args],
                                capture_output=True, timeout=20, env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ResuError('Local Git evidence could not be read.') from exc
    if result.returncode:
        raise ResuError('Requested Git object is unavailable in this repository.')
    return result.stdout


def verify_blob(record):
    repo = Path(record['repository']).expanduser()
    if not repo.is_dir():
        return {'state': 'unavailable', 'reason': 'Local repository is unavailable.'}
    commit, path = record['commit'], record['path']
    try:
        if _git(repo, 'cat-file', '-t', commit).strip() != b'commit':
            raise ResuError('Evidence must reference a commit object.')
        tree = _git(repo, 'ls-tree', '-z', commit, '--', path)
        entries = tree.rstrip(b'\0').split(b'\0') if tree else []
        if len(entries) != 1:
            raise ResuError('Evidence file does not exist at the pinned commit.')
        meta, name = entries[0].split(b'\t', 1)
        mode, kind, oid = meta.split()
        if name.decode('utf-8') != path or mode not in (b'100644', b'100755') or kind != b'blob':
            raise ResuError('Only regular committed text files are supported; symlinks/submodules are refused.')
        if int(_git(repo, 'cat-file', '-s', oid.decode())) > 2_000_000:
            raise ResuError('Evidence file exceeds the 2 MB text limit.')
        raw = _git(repo, 'cat-file', 'blob', oid.decode())
        if b'\0' in raw:
            raise ResuError('Binary evidence is unsupported.')
        lines = raw.decode('utf-8').splitlines()
        if record['end_line'] > len(lines):
            raise ResuError('Evidence line range is outside the file.')
        excerpt = '\n'.join(lines[record['start_line'] - 1:record['end_line']])
        if excerpt != record['excerpt']:
            raise ResuError('Excerpt differs from the pinned file lines.')
        return {'state': 'verified', 'blob_hash': oid.decode(), 'excerpt_hash': content_hash(excerpt)}
    except (ResuError, UnicodeError, ValueError) as exc:
        return {'state': 'invalid', 'reason': str(exc)}


def _links(record):
    prof = profile.load()
    entry = next((p for p in prof.get('projects', []) if p['id'] == record['project_id']), None)
    bullet = next((b for b in (entry or {}).get('bullets', []) if b['id'] == record['bullet_id']), None)
    if entry is None or bullet is None:
        raise ResuError('Evidence must link an existing profile project and one of its bullets.')
    return content_hash({'project': entry, 'bullet': bullet})


def normalize(data):
    input_schema.check(data, SPEC, 'project evidence')
    if any(not isinstance(data.get(k), str) or not data[k].strip() for k in SPEC if k not in ('start_line', 'end_line', 'outcome')):
        raise ResuError('Evidence requires repository, commit, path, excerpt, observed fact, project/bullet IDs and contribution.')
    clean = dict(data)
    clean['outcome'] = clean.get('outcome', '')
    if not re.fullmatch(r'[0-9a-fA-F]{40}|[0-9a-fA-F]{64}', clean['commit']):
        raise ResuError('Use an explicit full Git commit ID, never a branch or tag.')
    clean['commit'] = clean['commit'].lower()
    path = PurePosixPath(clean['path'])
    if path.is_absolute() or '..' in path.parts or str(path) != clean['path'] or '\\' in clean['path'] or '\x00' in clean['path']:
        raise ResuError('Evidence path must be a normalized repository-relative path.')
    if type(clean.get('start_line')) is not int or type(clean.get('end_line')) is not int or not 1 <= clean['start_line'] <= clean['end_line']:
        raise ResuError('Evidence requires a positive inclusive line range.')
    clean['repository'] = str(Path(clean['repository']).expanduser().resolve())
    return clean


def load():
    require_v2()
    data = store.read_json(store.home() / 'project_evidence.json', {'version': 1, 'records': []})
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('records'), list):
        raise ResuError('Evidence ledger is damaged; restore a valid backup.')
    seen = set()
    for row in data['records']:
        if (not isinstance(row, dict) or not isinstance(row.get('id'), str) or not re.fullmatch(r'pe[1-9]\d*', row['id'])
                or row['id'] in seen or row.get('state') not in ('proposed', 'confirmed', 'retired', 'needs_review')
                or not isinstance(row.get('source_fingerprint'), str) or not isinstance(row.get('evidence'), dict)
                or not isinstance(row.get('evidence_fingerprint'), str) or not isinstance(row.get('verification'), dict)
                or not isinstance(row.get('verified_at'), str) or (row.get('confirmed_at') is not None and not isinstance(row['confirmed_at'], str))):
            raise ResuError('Evidence record is damaged; restore a valid backup.')
        normalize(row['evidence'])
        seen.add(row['id'])
    return data


def save(data):
    store.write_json(store.home() / 'project_evidence.json', data)


def propose(data):
    ledger = load()
    clean = normalize(data)
    fingerprint = _links(clean)
    verification = verify_blob(clean)
    if verification['state'] != 'verified':
        raise ResuError(verification['reason'])
    ident = 'pe' + str(max((int(r['id'][2:]) for r in ledger['records']), default=0) + 1)
    row = {'id': ident, 'state': 'proposed', 'evidence': clean, 'source_fingerprint': fingerprint,
           'evidence_fingerprint': content_hash(clean), 'verification': verification, 'verified_at': now_iso(), 'confirmed_at': None}
    ledger['records'].append(row)
    save(ledger)
    return row


def status(row, verify=True):
    if content_hash(row['evidence']) != row['evidence_fingerprint']:
        return {'state': 'needs_review', 'reason': 'Evidence citation or attestation changed; propose and review a new record.'}
    try:
        if _links(row['evidence']) != row['source_fingerprint']:
            return {'state': 'needs_review', 'reason': 'Linked profile project or bullet changed.'}
    except ResuError as exc:
        return {'state': 'needs_review', 'reason': str(exc)}
    return verify_blob(row['evidence']) if verify else row['verification']


def action(ident, operation):
    data = load()
    row = next((r for r in data['records'] if r['id'] == ident), None)
    if row is None:
        raise ResuError('Unknown project evidence ID.')
    if operation == 'retire':
        row['state'] = 'retired'
    else:
        if row['state'] == 'retired':
            raise ResuError('Retired evidence cannot be confirmed; propose a new record.')
        checked = status(row)
        if checked['state'] != 'verified':
            if checked['state'] != 'unavailable':
                row['state'] = 'needs_review'
                save(data)
            raise ResuError(checked['reason'])
        row.update(state='confirmed', confirmed_at=now_iso(), verified_at=now_iso(), verification=checked)
    save(data)
    return row


def check(ident=None):
    data = load()
    selected = [r for r in data['records'] if ident is None or r['id'] == ident]
    if ident and not selected:
        raise ResuError('Unknown project evidence ID.')
    result = []
    for row in selected:
        checked = status(row)
        result.append({'id': row['id'], 'confirmation': row['state'], **checked})
        if checked['state'] not in ('verified', 'unavailable') and row['state'] == 'confirmed':
            row['state'] = 'needs_review'
    save(data)
    return result


def resolve(ids):
    records = {r['id']: r for r in load()['records']}
    resolved = []
    for ident in ids:
        row = records.get(ident)
        if row is None or row['state'] != 'confirmed':
            raise ResuError('Derivative claims require confirmed active evidence: ' + str(ident))
        checked = status(row)
        if checked['state'] != 'verified':
            raise ResuError('Evidence cannot currently be verified: ' + checked['reason'])
        resolved.append(row)
    return resolved
