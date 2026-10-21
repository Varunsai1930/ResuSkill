"""Read-only recorded outcomes and current-profile gaps; never infer rejection causes."""

from __future__ import annotations

import json

from . import checklist, jobs, profile
from .skills import canon
from .util import ResuError, norm_text, now_iso

ACTIONS = {
    'missing_evidence': 'Confirm relevant experience or add supporting evidence; absence from the profile is not proof of a missing skill.',
    'confirmed_skill_gap': 'Consider learning or demonstrating the confirmed missing skill if these roles remain a priority.',
    'confirmed_mismatch': 'Review whether this requirement fits your qualifications or preferences.',
    'user_assessed_gap': 'Review the recorded user assessment and its reason.',
    'evidence_needs_review': 'Reconfirm the changed evidence before relying on it.',
}


def _group_key(req: dict, kind: str) -> str:
    criterion = req.get('criterion')
    if criterion and criterion['type'] == 'skill':
        criterion = dict(criterion, skills=sorted({canon(s) for s in criterion['skills']}))
    return json.dumps([kind, req['importance'], criterion or norm_text(req['text'])], sort_keys=True)


def report() -> dict:
    errors = []
    saved = jobs.list_jobs(errors)
    counts = {status: 0 for status in jobs.STATUSES}
    valid = []
    for job in saved:
        status = job['tracking']['status']
        if status not in counts:
            errors.append((job['id'], 'Unrecognized tracking status; excluded from this report.'))
            continue
        counts[status] += 1
        valid.append(job)
    warnings = ['Statuses are the latest recorded states, not a conversion funnel. No rejection causes are inferred.',
                'Gaps use the current profile across readable saved jobs, including closed applications; they are not submission-time assessments.']
    try:
        prof = profile.load(required=False)
    except ResuError as exc:
        prof = None
        errors.append(('profile', str(exc)))
    if prof is None:
        warnings.append('No usable profile: outcomes are available, but gaps have not been evaluated.')
    groups = {}
    evaluated = 0
    unreviewed = []
    if prof:
        for job in valid:
            if not job['requirements'] and not job.get('requirements_reviewed_at'):
                unreviewed.append(job['id'])
                continue
            evaluated += 1
            for req, row in zip(job['requirements'], checklist.evaluate(job, prof)):
                if row['stale_links']:
                    kind = 'evidence_needs_review'
                elif row['status'] == checklist.MET:
                    continue
                elif row['status'] == checklist.UNKNOWN:
                    kind = 'missing_evidence'
                elif row['overridden']:
                    kind = 'user_assessed_gap'
                elif (req.get('criterion') or {}).get('type') == 'skill':
                    kind = 'confirmed_skill_gap'
                else:
                    kind = 'confirmed_mismatch'
                key = _group_key(req, kind)
                group = groups.setdefault(key, {
                    'kind': kind, 'requirement': req['text'], 'criterion': req.get('criterion'),
                    'importance': req['importance'], 'action': ACTIONS[kind], 'occurrences': [],
                })
                group['occurrences'].append({'job_id': job['id'], 'requirement_id': req['id'],
                                             'status': row['status'], 'basis': row['basis'],
                                             'excerpt': row['excerpt']})
    gaps = list(groups.values())
    for gap in gaps:
        gap['job_count'] = len({r['job_id'] for r in gap['occurrences']})
    gaps.sort(key=lambda g: (-g['job_count'], g['kind'], g['requirement'], g['importance']))
    return {'generated_at': now_iso(), 'recorded_jobs': len(valid), 'outcomes': counts,
            'profile_revision': prof['_meta']['revision'] if prof else None,
            'jobs_evaluated_for_gaps': evaluated, 'unreviewed_jobs': unreviewed,
            'gaps': gaps, 'warnings': warnings,
            'errors': [{'id': jid, 'message': message} for jid, message in errors]}


def text_report(result: dict) -> str:
    lines = [f"Recorded outcomes ({result['recorded_jobs']} jobs)",
             ', '.join(f'{status}: {count}' for status, count in result['outcomes'].items()),
             f"Current gaps ({result['jobs_evaluated_for_gaps']} jobs evaluated)"]
    for gap in result['gaps']:
        lines.append(f"- {gap['kind']} | {gap['importance']} | {gap['requirement']} | {gap['job_count']} job(s)")
        lines.append('  ' + gap['action'])
        for row in gap['occurrences']:
            lines.append(f"  {row['job_id']}/{row['requirement_id']}: {row['basis']}")
    if result['unreviewed_jobs']:
        lines.append('Requirements not reviewed: ' + ', '.join(result['unreviewed_jobs']))
    lines.extend('Note: ' + warning for warning in result['warnings'])
    lines.extend(f"Error: {error['id']}: {error['message']}" for error in result['errors'])
    return '\n'.join(lines)
