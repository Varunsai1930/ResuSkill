"""User-scheduled local follow-ups; never sends messages or starts a scheduler."""
from __future__ import annotations

from datetime import date
import re

from . import jobs
from .util import ResuError, now_iso

TERMINAL = {'rejected', 'withdrawn', 'offer'}
STATES = {'active', 'completed', 'cancelled', 'inactive'}


def calendar_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ResuError('Follow-up date must be a full YYYY-MM-DD calendar date.')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ResuError('Follow-up date is not a real calendar date.') from None


def validate(records):
    if not isinstance(records, list):
        raise ResuError('Stored follow-ups must be a list; restore a valid backup.')
    seen = set()
    for row in records:
        if (not isinstance(row, dict) or not isinstance(row.get('id'), str)
                or not re.fullmatch(r'f[1-9]\d*', row['id']) or row['id'] in seen
                or not isinstance(row.get('state'), str) or row['state'] not in STATES
                or any(not isinstance(row.get(key), str) for key in ('date', 'note', 'created_at', 'updated_at'))):
            raise ResuError('Stored follow-up is damaged or duplicated; restore a valid backup.')
        calendar_date(row['date'])
        seen.add(row['id'])
    return records


def rows(job, today=None):
    today = today or date.today()
    result = []
    for original in validate(job['tracking'].get('followups', [])):
        row = dict(original)
        # Even legacy/manually edited terminal records cannot produce active reminders.
        if row['state'] == 'active' and job['tracking']['status'] in TERMINAL:
            row['state'] = 'inactive'
        due = calendar_date(row['date'])
        row['timing'] = ('overdue' if due < today else 'due_today' if due == today else 'upcoming') if row['state'] == 'active' else row['state']
        result.append(row)
    return sorted(result, key=lambda r: (r['state'] != 'active', r['date'], int(r['id'][1:])))


def set_followup(job_id, due, note='', ident=None):
    calendar_date(due)
    if not isinstance(note, str):
        raise ResuError('Follow-up note must be text.')
    job = jobs.load(job_id)
    if job['tracking']['status'] in TERMINAL:
        raise ResuError('Reopen the application before setting an active follow-up.')
    records = validate(job['tracking'].get('followups', []))
    now = now_iso()
    if ident:
        row = next((r for r in records if r['id'] == ident), None)
        if row is None or row['state'] in ('completed', 'cancelled'):
            raise ResuError('Follow-up is missing or finished; create a new follow-up instead.')
        row.update(date=due, note=note.strip(), state='active', updated_at=now)
    else:
        ident = 'f' + str(max((int(r['id'][1:]) for r in records), default=0) + 1)
        row = dict(id=ident, date=due, note=note.strip(), state='active', created_at=now, updated_at=now)
        records.append(row)
    job['tracking']['followups'] = records
    jobs.save(job)
    return row


def finish(job_id, ident, state):
    if state not in ('completed', 'cancelled'):
        raise ResuError('Invalid follow-up completion state.')
    job = jobs.load(job_id)
    row = next((r for r in validate(job['tracking'].get('followups', [])) if r['id'] == ident), None)
    if row is None:
        raise ResuError('No follow-up with that ID.')
    if row['state'] in ('completed', 'cancelled'):
        if row['state'] == state:
            return row
        raise ResuError('A finished follow-up cannot be changed; create a new follow-up.')
    row.update(state=state, updated_at=now_iso())
    jobs.save(job)
    return row


def suppress(job, new_status):
    records = validate(job['tracking'].get('followups', []))
    if new_status in TERMINAL or job['tracking']['status'] in TERMINAL:
        for row in records:
            if row['state'] == 'active':
                row.update(state='inactive', updated_at=now_iso())
