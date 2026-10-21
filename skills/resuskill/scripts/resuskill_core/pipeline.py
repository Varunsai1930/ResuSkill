"""Read-only application pipeline with explicit, advisory next actions."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from . import checklist, jobs, listing, package, profile
from .util import ResuError, now_iso


def _next_action(row: dict, has_profile: bool) -> dict:
    status = row['status']
    if status in ('rejected', 'withdrawn'):
        return {'priority': 9, 'code': 'closed', 'text': 'No active application action. Review recorded outcomes when useful.'}
    if status == 'offer':
        return {'priority': 1, 'code': 'review_offer', 'text': 'Review the offer and record your decision; no decision is inferred.'}
    if status in ('applied', 'assessment', 'interview'):
        return {'priority': 2, 'code': 'record_progress', 'text': 'Check your employer correspondence and record the next step or outcome. No follow-up date is recorded here.'}
    if row['listing']['state'] in ('closed', 'expired'):
        return {'priority': 1, 'code': 'recheck_listing', 'text': 'Recheck the closed or expired posting before spending more time or applying.'}
    if not has_profile:
        return {'priority': 1, 'code': 'set_up_profile', 'text': 'Create or repair the confirmed profile so this package can be checked.'}
    if row['listing']['state'] != 'observed_open':
        return {'priority': 2, 'code': 'recheck_listing', 'text': 'Check the employer posting and record a fresh listing observation.'}
    if row['blockers']:
        return {'priority': 3, 'code': 'resolve_blockers', 'text': 'Resolve the package blockers below, then review the package.'}
    if row['pending_resume'] or row['pending_answers']:
        return {'priority': 4, 'code': 'review_drafts', 'text': 'Review pending drafts with their sources. Accept only the changes you want.'}
    if row['review'] == package.STALE:
        return {'priority': 5, 'code': 'review_stale', 'text': 'Review the changed profile or job and approve the package again if it is still accurate.'}
    if row['review'] == package.DRAFT:
        return {'priority': 5, 'code': 'review_package', 'text': 'Review the resume, answers and fit warnings, then explicitly approve if ready.'}
    if row['warnings']:
        return {'priority': 6, 'code': 'review_warnings', 'text': 'Review the remaining listing and fit warnings before deciding whether to submit.'}
    return {'priority': 7, 'code': 'submit_manually', 'text': 'Submit the approved package yourself, then record Applied only after submission.'}


def report() -> dict:
    problems = []
    saved = jobs.list_jobs(problems)
    try:
        prof = profile.load(required=False)
    except ResuError as exc:
        prof = None
        problems.append(('profile', str(exc)))
    rows = []
    for job in saved:
        row = {'id': job['id'], 'company': job['company'], 'title': job['title'],
               'status': job['tracking']['status'], 'review': 'unreadable', 'listing': None,
               'checklist': None, 'blockers': [], 'warnings': [], 'pending_resume': False, 'pending_answers': []}
        try:
            if row['status'] not in jobs.STATUSES:
                raise ResuError('Unrecognized tracking status; restore a valid record.')
            row['listing'] = listing.assess(job)
            pkg = package.load(job['id'])
            proposal = package.load_proposal(job['id'])
            row['review'] = package.review_state(job, pkg, prof)
            row['pending_resume'] = bool(proposal and proposal['proposal'] != pkg.get('resume'))
            row['pending_answers'] = sorted(pkg['answer_proposals'])
            if prof:
                row['blockers'], row['warnings'] = package.check(job['id'])
                fit = checklist.evaluate(job, prof)
                row['checklist'] = checklist.summary(fit)
                for req in fit:
                    if req['status'] != checklist.MET or req['stale_links']:
                        row['warnings'].append(f"{req['id']} ({req['importance']}, {req['status']}): {req['text']} — {req['basis']}")
            else:
                row['blockers'] = ['No usable profile; current package checks have not run.']
                row['warnings'] = row['listing']['warnings']
            row['next_action'] = _next_action(row, prof is not None)
        except ResuError as exc:
            problems.append((job['id'], str(exc)))
            row['review'] = 'unreadable'
            row['blockers'] = [str(exc)]
            row['next_action'] = {'priority': 0, 'code': 'repair_record', 'text': 'Repair the unreadable record from a valid backup before relying on this row.'}
        rows.append(row)
    present = {row['id'] for row in rows}
    for jid, message in problems:
        if jid == 'profile' or jid in present:
            continue
        rows.append({'id': jid, 'company': '', 'title': 'Unreadable job', 'status': 'unreadable',
                     'review': 'unreadable', 'listing': None, 'checklist': None, 'blockers': [message],
                     'warnings': [], 'pending_resume': False, 'pending_answers': [],
                     'next_action': {'priority': 0, 'code': 'repair_record', 'text': 'Restore a valid job record; no application state can be inferred.'}})
    rows.sort(key=lambda row: (row['next_action']['priority'], row['company'].casefold(), row['id']))
    return {'generated_at': now_iso(), 'jobs': rows,
            'notes': ['Local snapshot: regenerate to see later changes. Listing observations are not live checks.',
                      'Next actions are suggestions, not approval or submission. No messages are sent or follow-ups scheduled.',
                      'Package checks use the current profile; submitted snapshots are not altered.'],
            'errors': [{'id': jid, 'message': message} for jid, message in problems]}


def text_report(result: dict) -> str:
    lines = [f"Application pipeline — {len(result['jobs'])} job(s)"]
    for row in result['jobs']:
        observation = row['listing'] or {}
        lines.extend([f"\n{row['company']} — {row['title']} ({row['id']})",
                      f"{row['status']} | review: {row['review']} | listing: {observation.get('state', 'unreadable')} | deadline: {observation.get('deadline') or 'unknown'}",
                      'Next: ' + row['next_action']['text']])
        lines.extend('  Blocker: ' + text for text in row['blockers'])
        lines.extend('  Warning: ' + text for text in row['warnings'])
    lines.extend('Note: ' + note for note in result['notes'])
    lines.extend(f"Error: {err['id']}: {err['message']}" for err in result['errors'])
    return '\n'.join(lines)


def html_report(result: dict) -> str:
    def e(value):
        return escape(str(value), quote=True)

    def items(values):
        return '<ul>' + ''.join('<li>' + e(value) + '</li>' for value in values) + '</ul>'

    cards = []
    for row in result['jobs']:
        observation = row['listing'] or {}
        fit = row['checklist']
        counts = (f"{fit['met']} met · {fit['unmet']} unmet · {fit['unknown']} unknown") if fit else 'Not evaluated'
        source = (f'<a href="{e(observation["source_url"])}">Recorded listing source</a>'
                  if observation.get('source_url') else 'No listing source recorded')
        cards.append(f'<article><h2>{e(row["company"])} — {e(row["title"])}</h2><p class="meta">{e(row["id"])}</p>'
                     f'<p><b>{e(row["status"])}</b> · Review: {e(row["review"])} · Listing: {e(observation.get("state", "unreadable"))}</p>'
                     f'<p>Deadline: {e(observation.get("deadline") or "Unknown")} · {source}</p>'
                     f'<p>Checklist: {e(counts)}</p><p class="action"><b>Next:</b> {e(row["next_action"]["text"])}</p>'
                     + ('<h3>Package blockers</h3>' + items(row['blockers']) if row['blockers'] else '')
                     + ('<details><summary>Warnings and fit evidence</summary>' + items(row['warnings']) + '</details>' if row['warnings'] else '')
                     + (f'<p>Pending: {"resume draft; " if row["pending_resume"] else ""}{e(", ".join(row["pending_answers"]))}</p>' if row['pending_resume'] or row['pending_answers'] else '')
                     + '</article>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Application pipeline</title><style>body{font:16px/1.6 system-ui,sans-serif;color:#172b3a;background:#f4f6f8;max-width:960px;margin:32px auto;padding:0 20px}'
            'h1{margin-bottom:0}h2{font-size:21px;margin:0}h3{font-size:16px}article{background:white;border:1px solid #cbd5df;border-radius:12px;padding:24px;margin:20px 0}'
            '.meta{color:#536373;font-size:13px}.action{background:#e8f1f7;padding:12px;border-left:4px solid #286082}li,p{overflow-wrap:anywhere}summary{cursor:pointer}a{color:#185887}</style></head><body>'
            f'<h1>Application pipeline</h1><p class="meta">{len(result["jobs"])} jobs · Generated {e(result["generated_at"])}</p>'
            + items(result['notes'])
            + ('<h2>Incomplete data</h2>' + items([err['id'] + ': ' + err['message'] for err in result['errors']]) if result['errors'] else '')
            + (''.join(cards) or '<p>No saved jobs yet.</p>') + '</body></html>')


def export(result: dict, output: str) -> dict:
    target = Path(output).expanduser().resolve()
    # A new folder avoids overwriting candidate data or previous reports.
    if Path(output).expanduser().is_symlink() or target.exists():
        raise ResuError('Pipeline output must be a new directory.')
    target.mkdir(parents=True)
    (target / 'index.html').write_text(html_report(result), encoding='utf-8')
    (target / 'report.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    return {'html': str(target / 'index.html'), 'json': str(target / 'report.json')}
