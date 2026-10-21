"""Submission cohorts from recorded dates and immutable submission snapshots."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import jobs, store
from .followups import calendar_date
from .listing import timestamp
from .util import ResuError, now_iso


def _time(value):
    if not isinstance(value, str):
        raise ResuError('Missing or invalid submission/history timestamp.')
    try:
        parsed = timestamp(value)
    except (ValueError, TypeError):
        raise ResuError('Submission/history timestamp must include a valid timezone.') from None
    if parsed > datetime.now(timezone.utc):
        raise ResuError('Submission/history timestamp is in the future.')
    return parsed


def _stages(job, applied):
    history = job['tracking'].get('history')
    if not isinstance(history, list) or not history:
        raise ResuError('Missing or malformed tracking history; reached stages unavailable.')
    previous = None
    stages = set()
    for row in history:
        if not isinstance(row, dict) or not isinstance(row.get('status'), str) or row['status'] not in jobs.STATUSES:
            raise ResuError('Invalid history status; reached stages unavailable.')
        when = _time(row.get('at'))
        if previous is not None and when < previous:
            raise ResuError('History timestamps are out of order; reached stages unavailable.')
        if row['status'] != 'saved' and when < applied:
            raise ResuError('Outcome precedes submission; reached stages unavailable.')
        previous = when
        if when >= applied:
            stages.add(row['status'])
    if history[-1]['status'] != job['tracking']['status'] or 'applied' not in stages:
        raise ResuError('Current status or submission contradicts history; reached stages unavailable.')
    return stages


def _frozen(job):
    name = job['tracking'].get('snapshot')
    if not isinstance(name, str) or not name or Path(name).name != name or name.startswith('.') or '\\' in name or '\x00' in name:
        raise ResuError('No valid submission snapshot reference; historical fit unavailable.')
    try:
        root = (store.job_dir(job['id']) / 'snapshots').resolve()
        path = root / name / 'package.json'
        if root not in path.resolve().parents:
            raise ResuError('Snapshot reference escapes its directory.')
        data = store.read_json(path)
    except (OSError, ValueError, RuntimeError) as exc:
        raise ResuError('Snapshot path is unreadable; historical fit unavailable.') from exc
    if not isinstance(data, dict) or not isinstance(data.get('job'), dict) or data['job'].get('id') != job['id']:
        raise ResuError('Missing or invalid submission snapshot; historical fit unavailable.')
    rows = data.get('checklist')
    if not isinstance(rows, list):
        raise ResuError('Missing frozen checklist; historical fit unavailable.')
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or any(not isinstance(row.get(k), str) for k in ('id', 'text', 'status', 'importance', 'basis'))
                or row['id'] in seen or row['status'] not in ('met', 'unmet', 'unknown')
                or row['importance'] not in ('required', 'preferred', 'unspecified')):
            raise ResuError('Damaged frozen checklist; historical fit unavailable.')
        seen.add(row['id'])
    return rows


def report(start=None, end=None):
    start_date = calendar_date(start) if start else None
    end_date = calendar_date(end) if end else None
    if start_date and end_date and start_date > end_date:
        raise ResuError('Submission date range is reversed.')
    errors = []
    saved = jobs.list_jobs(errors)
    excluded, cohort = [], []
    current = {status: 0 for status in jobs.STATUSES}
    reached = {status: 0 for status in jobs.STATUSES}
    history_n = fit_n = 0
    for job in saved:
        try:
            applied = _time(job['tracking'].get('applied_at'))
            if job['tracking']['status'] not in current:
                raise ResuError('Unrecognized current tracking status.')
        except ResuError as exc:
            excluded.append({'id': job['id'], 'reason': str(exc)})
            continue
        # Use the recorded timestamp's own calendar date, not the machine timezone.
        day = applied.date()
        if (start_date and day < start_date) or (end_date and day > end_date):
            excluded.append({'id': job['id'], 'reason': 'Outside the requested submission dates.'})
            continue
        row = {'id': job['id'], 'submitted_at': job['tracking']['applied_at'], 'status': job['tracking']['status'],
               'reached_stages': None, 'submission_checklist': None}
        current[row['status']] += 1
        try:
            stages = _stages(job, applied)
            history_n += 1
            row['reached_stages'] = sorted(stages)
            for stage in stages:
                reached[stage] += 1
        except ResuError as exc:
            errors.append((job['id'], str(exc)))
        try:
            row['submission_checklist'] = _frozen(job)
            fit_n += 1
        except ResuError as exc:
            errors.append((job['id'], str(exc)))
        cohort.append(row)
    return {'mode': 'historical', 'generated_at': now_iso(), 'from': start, 'to': end,
            'cohort_count': len(cohort), 'current_status': current, 'reached_stages': reached,
            'history_denominator': history_n, 'fit_denominator': fit_n,
            'reached_percentages': {s: round(n * 100 / history_n, 2) for s, n in reached.items()} if history_n >= 10 else None,
            'applications': cohort, 'excluded': excluded,
            'errors': [{'id': jid, 'message': message} for jid, message in errors],
            'notes': ['Inclusive submission dates use each recorded timestamp timezone.',
                      'Reached stages count each application once; invalid histories are excluded from that denominator.',
                      'Percentages are hidden below 10 eligible histories as a display policy, not statistical significance.',
                      'Historical fit comes only from frozen checklists; current profile is never substituted. No rejection causes are inferred.']}


def text_report(result):
    import json
    return json.dumps(result, indent=2, ensure_ascii=False)
