"""Export explicitly selected jobs without accepting or approving their drafts."""
from pathlib import Path
import json
import zipfile
from html import escape

from . import jobs, listing, package, profile, render, store, style as style_mod
from .util import ResuError
from .validate import validate_proposal


def export(job_ids, output, want_pdf=False, accepted=False, style=None):
    if not job_ids or len(set(job_ids)) != len(job_ids):
        raise ResuError("Select at least one job, with no duplicate IDs")
    target = Path(output).expanduser()
    if target.exists() or target.is_symlink():
        raise ResuError("Batch output must be a new directory")
    settings = style_mod.normalize(style) if style is not None else None
    prof = profile.load()
    prepared = []
    # Validate every selection before creating the pack; never silently omit a bad draft.
    for job_id in job_ids:
        job = jobs.load(job_id)
        pkg = package.load(job_id)
        proposal = package.load_proposal(job_id)
        resume = pkg.get('resume') if accepted else (proposal or {}).get('proposal')
        if not resume:
            raise ResuError(f"{job_id}: no {'accepted resume' if accepted else 'pending proposal'}")
        clean, warnings = validate_proposal(prof, job, resume)
        presentation = settings if settings is not None else style_mod.saved(store.job_dir(job_id) / 'out')
        prepared.append((job, pkg, proposal, clean, warnings, presentation))
    target.mkdir(parents=True)
    result = {'mode': 'accepted' if accepted else 'proposal', 'approved_for_submission': False,
              'jobs': [], 'errors': [], 'output': str(target)}
    files = []
    links = []
    for index, (job, pkg, proposal, resume, warnings, presentation) in enumerate(prepared, 1):
        folder = target / f"{index:02d}-{job['id']}"
        folder.mkdir()
        observation = listing.assess(job)
        item = {'job': job['id'], 'company': job['company'], 'title': job['title'],
                'listing': observation, 'warnings': warnings, 'files': []}
        for name, body in [('resume.html', render.resume_html(prof, resume, 'Resume', presentation)),
                           ('review.html', render.review_html(job, prof, pkg, proposal))]:
            path = folder / name
            path.write_text(body, encoding='utf-8')
            files.append(path)
            item['files'].append(path.relative_to(target).as_posix())
        if want_pdf:
            try:
                path = render.print_pdf(folder / 'resume.html', folder / 'resume.pdf')
                files.append(path)
                item['files'].append(path.relative_to(target).as_posix())
            except (ResuError, OSError) as exc:
                message = f"{job['id']}: {exc}"
                result['errors'].append(message)
                item['pdf_error'] = str(exc)
        result['jobs'].append(item)
        anchors = ' | '.join(f'<a href="{escape(p, quote=True)}">{escape(Path(p).name)}</a>' for p in item['files'])
        notes = warnings + observation['warnings']
        links.append(f"<li><h2>{escape(job['company'])} — {escape(job['title'])}</h2>"
                     f"<p>{anchors}</p><p>{escape('; '.join(notes))}</p>"
                     f"<p>{escape(item.get('pdf_error', ''))}</p></li>")
    (target / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Resume pack</title>'
        '<h1>Resume pack — review required</h1><p>Export does not accept drafts, approve packages, '
        'or submit applications. Review each resume and its evidence before use.</p><ol>' + ''.join(links) + '</ol>', encoding='utf-8')
    (target / 'report.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    files.extend([target / 'index.html', target / 'report.json'])
    # Explicit allowlist: never bundle old PDFs, snapshots, or the complete profile.
    with zipfile.ZipFile(target / 'resumes.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(target).as_posix())
    return result
