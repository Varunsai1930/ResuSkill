"""Recorded observations of public postings, distinct from application status."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

from . import input_schema
from .util import ResuError

DEFAULT = {"status": "unknown", "verified_at": None, "source_url": "", "status_excerpt": "",
           "deadline": None, "program_start": None, "program_end": None, "intake_note": "",
           "eligibility": "unknown", "eligibility_note": ""}
STALE_DAYS = 7


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    return parsed


def normalize(data) -> dict:
    input_schema.check(data, {k: input_schema.TEXT for k in DEFAULT}, "listing")
    result = dict(DEFAULT)
    result.update(data)
    for key, default in DEFAULT.items():
        if default is not None:
            result[key] = (result[key] or "").strip()
    if result['status'] not in ('unknown', 'open', 'closed'):
        raise ResuError("listing.status must be unknown, open or closed")
    if result['eligibility'] not in ('unknown', 'preference_match', 'conditional', 'mismatch'):
        raise ResuError("listing.eligibility must be unknown, preference_match, conditional or mismatch")
    if result['eligibility'] in ('conditional', 'mismatch') and not result['eligibility_note']:
        raise ResuError("listing.eligibility_note must explain conditions or mismatches")
    if result['source_url']:
        try:
            url = urlsplit(result['source_url'])
            valid = url.scheme in ('http', 'https') and bool(url.hostname) and not url.username and not url.password
        except ValueError:
            valid = False
        if not valid:
            raise ResuError("listing.source_url must be a public HTTP(S) URL without credentials")
    if result['status'] != 'unknown' and not all(result[k] for k in ('verified_at', 'source_url', 'status_excerpt')):
        raise ResuError("Open/closed observations need verified_at, source_url and a verbatim status_excerpt; the CLI cannot verify the page itself")
    for key in ('verified_at', 'deadline', 'program_start', 'program_end'):
        value = result[key]
        if not value:
            result[key] = None
            continue
        try:
            if key == 'verified_at' or (key == 'deadline' and len(value) != 10):
                timestamp(value)
            else:
                if len(value) != 10:
                    raise ValueError("full date required")
                date.fromisoformat(value)
        except (ValueError, TypeError):
            raise ResuError(f"listing.{key}: use YYYY-MM-DD, or a timezone-aware ISO timestamp for verified_at/deadline") from None
    if result['program_start'] and result['program_end'] and result['program_start'] > result['program_end']:
        raise ResuError("listing.program_start must not be after program_end")
    return result


def assess(job: dict, now: datetime | None = None) -> dict:
    info = normalize(job.get('listing') or {})
    now = now or datetime.now().astimezone()
    warnings = []
    verified = timestamp(info['verified_at']) if info['verified_at'] else None
    deadline = info['deadline']
    expired = bool(deadline and (date.fromisoformat(deadline) < now.date() if len(deadline) == 10 else timestamp(deadline) < now))
    if info['status'] == 'closed':
        state = 'closed'
        warnings.append('The recorded observation says the listing is closed; recheck before applying.')
    elif expired:
        state = 'expired'
        warnings.append('The recorded application deadline has passed; do not count this as a current opening.')
    elif verified and verified > now + timedelta(minutes=5):
        state = 'unverified'
        warnings.append('The verification timestamp is in the future; correct it before relying on the observation.')
    elif info['status'] == 'unknown' or not verified:
        state = 'unverified'
        warnings.append('No verified open-listing observation is recorded. Saving a job does not verify that it is open.')
    elif now - verified > timedelta(days=STALE_DAYS):
        state = 'stale'
        warnings.append(f'The last open-listing observation is older than {STALE_DAYS} days; recheck the source.')
    else:
        state = 'observed_open'
    if not deadline:
        warnings.append('Application deadline is unknown.')
    if info['program_end'] and date.fromisoformat(info['program_end']) < now.date():
        warnings.append('The recorded program end date has passed; confirm a new intake before applying.')
    if info['eligibility'] in ('conditional', 'mismatch'):
        warnings.append(f"Eligibility {info['eligibility']}: {info['eligibility_note']}")
    elif info['eligibility'] == 'unknown':
        warnings.append('Location, graduation and availability eligibility have not been recorded as reviewed.')
    if info['intake_note']:
        warnings.append('Intake: ' + info['intake_note'])
    return {**info, 'state': state, 'warnings': warnings}
