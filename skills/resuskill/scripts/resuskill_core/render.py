"""Render the resume and the review page as HTML, and optionally print the resume to PDF.

Names, employers, titles, dates, degrees and contact details always come from the
profile. Only bullet text, summary text, ordering and skill selection come from the
validated package. Every value is HTML-escaped.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
from difflib import SequenceMatcher
from html import escape
from pathlib import Path
from string import Template

from . import checklist as checklist_mod
from . import package as package_mod
from . import profile as profile_mod
from . import store, validate, listing, style as style_mod
from .skills import canon
from .util import ResuError, content_hash, slugify

TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "assets" / "resume_template.html"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_date(value: str | None) -> str:
    if not value:
        return ""
    if value == "present":
        return "Present"
    parts = value.split("-")
    if len(parts) >= 2 and parts[1].isdigit():
        return f"{MONTHS[int(parts[1]) - 1]} {parts[0]}"
    return parts[0]


def date_range(entry: dict) -> str:
    start, end = fmt_date(entry.get("start")), fmt_date(entry.get("graduation") or entry.get("end"))
    if start and end:
        return f"{start} – {end}"
    return start or end


def _e(value) -> str:
    return escape(str(value or ""), quote=True)


def _link(url: str, label: str = "") -> str:
    href = url if url.startswith(("http://", "https://", "mailto:")) else f"https://{url}"
    shown = label or url.replace("https://", "").replace("http://", "").rstrip("/")
    return f'<a href="{_e(href)}">{_e(shown)}</a>'


def _row(what: str, when: str) -> str:
    return f'<div class="row"><span class="what">{what}</span><span class="when">{_e(when)}</span></div>'


def _missing_refs(prof: dict, resume: dict) -> list[str]:
    """IDs the resume uses that the current profile no longer has."""
    known = {e["id"] for e in prof.get("education") or []} | {c["id"] for c in prof.get("certifications") or []}
    missing = [i for i in list(resume.get("education") or []) + list(resume.get("certifications") or []) if i not in known]
    for section in ("experience", "projects"):
        missing += [item["entry"] for item in resume.get(section) or [] if not profile_mod.entry_by_id(prof, item["entry"])]
    return missing


def resume_body(prof: dict, resume: dict, style: dict | None = None) -> str:
    settings = style_mod.normalize(style)
    missing = _missing_refs(prof, resume)
    if missing:
        raise ResuError(
            f"The resume uses {', '.join(missing)}, which the profile no longer has. "
            "Write and accept a new proposal before rendering."
        )
    contact = prof["contact"]
    bits = []
    if contact.get("email"):
        bits.append(f'<span><a href="mailto:{_e(contact["email"])}">{_e(contact["email"])}</a></span>')
    bits += [f"<span>{_e(contact.get(k))}</span>" for k in ("phone", "location") if contact.get(k)]
    bits += [f"<span>{_link(url, name if settings['link_labels'] else '')}</span>" for name, url in (contact.get("links") or {}).items() if url]
    header = f'<header><h1>{_e(contact["name"])}</h1><div class="contact">{"".join(bits)}</div></header>'
    sections = {}

    if resume.get("summary"):
        sections['summary'] = f'<section><h2>Summary</h2><p class="summary">{_e(resume["summary"]["text"])}</p></section>'

    education = {e["id"]: e for e in prof.get("education") or []}
    if resume.get("education"):
        parts = []
        for edu_id in resume["education"]:
            edu = education[edu_id]
            degree = ", ".join(x for x in (edu.get("degree"), edu.get("field")) if x)
            main, secondary = (degree, edu["institution"]) if settings['degree_first'] else (edu["institution"], degree)
            sub = " • ".join(x for x in (secondary, _grade(edu.get("gpa"))) if x)
            bullets = "".join(f"<li>{_e(b['text'])}</li>" for b in edu.get("bullets") or [])
            parts.append(
                f'<div class="entry">{_row(_e(main), date_range(edu))}'
                f'<div class="sub">{_e(sub)}</div>{f"<ul>{bullets}</ul>" if bullets else ""}</div>'
            )
        sections['education'] = f"<section><h2>Education</h2>{''.join(parts)}</section>"

    for section, heading in (("experience", "Experience"), ("projects", "Projects")):
        items = resume.get(section) or []
        if not items:
            continue
        parts = []
        for item in items:
            entry = profile_mod.entry_by_id(prof, item["entry"])[1]
            if section == "experience":
                what = f"{_e(entry.get('title'))} — {_e(entry.get('organization'))}"
                sub = entry.get("location", "")
            else:
                what = _e(entry.get("name"))
                if entry.get("role"):
                    what += f" — {_e(entry['role'])}"
                sub = ", ".join(entry.get("technologies") or [])
            link = f" • {_link(entry['link'])}" if entry.get("link") else ""
            bullets = "".join(f"<li>{_e(b['text'])}</li>" for b in item["bullets"])
            parts.append(
                f'<div class="entry">{_row(what, date_range(entry))}'
                f'{f"<div class=sub>{_e(sub)}{link}</div>" if sub or link else ""}'
                f'{f"<ul>{bullets}</ul>" if bullets else ""}</div>'
            )
        if section == 'projects':
            heading = settings['projects_heading']
        sections[section] = f"<section><h2>{heading}</h2>{''.join(parts)}</section>"

    if resume.get("skills"):
        categories: dict[str, list[str]] = {}
        lookup = {canon(s["name"]): s.get("category") or "Skills" for s in prof.get("skills") or []}
        # Show each skill as the user spelled it in the profile (skills list first, then entry technologies).
        spelling: dict[str, str] = {}
        for s in prof.get("skills") or []:
            spelling.setdefault(canon(s["name"]), s["name"])
        for section in ("experience", "projects"):
            for entry in prof.get(section) or []:
                for tech in entry.get("technologies") or []:
                    spelling.setdefault(canon(tech), tech)
        for name in resume["skills"]:
            categories.setdefault(lookup.get(canon(name), "Skills"), []).append(spelling.get(canon(name), name))
        # Uncategorized skills go last, labelled "Other" when named categories exist.
        uncategorized = categories.pop("Skills", None)
        if uncategorized:
            categories["Other" if categories else "Skills"] = uncategorized
        rows = "".join(f"<p><b>{_e(cat)}:</b> {_e(', '.join(names))}</p>" for cat, names in categories.items())
        sections['skills'] = f'<section class="skills"><h2>{settings["skills_heading"]}</h2>{rows}</section>'

    certs = {c["id"]: c for c in prof.get("certifications") or []}
    if resume.get("certifications"):
        lines = []
        for cert_id in resume["certifications"]:
            cert = certs[cert_id]
            text = _e(cert["name"])
            if cert.get("issuer"):
                text += " — " + _e(cert["issuer"])
            if cert.get("date"):
                text += f" ({_e(fmt_date(cert['date']))})"
            lines.append(f"<li>{text}</li>")
        items = "".join(lines)
        sections['certifications'] = f"<section><h2>Certifications</h2><ul>{items}</ul></section>"
    return "\n".join([header] + [sections[key] for key in settings['section_order'] if key in sections])


def _grade(value) -> str:
    """ "3.7" -> "GPA 3.7"; a value with its own label ("CGPA: 8.88/10", "Score: 986/1000") as written."""
    text = str(value or "").strip()
    if not text:
        return ""
    return text if re.search(r"[A-Za-z]", text) else f"GPA {text}"


def resume_html(prof: dict, resume: dict, title: str, style: dict | None = None) -> str:
    template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    return template.substitute(title=_e(title), body=resume_body(prof, resume, style), style=style_mod.css(style))


# ---------------------------------------------------------------- review page

_REVIEW_CSS = """
:root { --bg:#fafafa; --card:#fff; --ink:#1b1b1b; --muted:#666; --line:#e2e2e2;
  --met:#1d7a46; --unmet:#b3261e; --unknown:#8a6d00; --add:#e8f5ec; --orig:#f4f4f4; }
@media (prefers-color-scheme: dark) { :root { --bg:#151515; --card:#1f1f1f; --ink:#ececec;
  --muted:#a0a0a0; --line:#333; --met:#5cc98a; --unmet:#f08a80; --unknown:#e0c060; --add:#1c3324; --orig:#262626; } }
* { box-sizing:border-box; }
body { margin:0; padding:24px 16px; background:var(--bg); color:var(--ink);
  font:14px/1.5 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width:980px; margin:0 auto; }
h1 { font-size:22px; margin:0 0 4px; } h2 { font-size:17px; margin:28px 0 10px; }
.meta { color:var(--muted); }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px 14px; margin:8px 0; }
.pill { display:inline-block; padding:1px 8px; border-radius:999px; font-size:12px; font-weight:600; border:1px solid currentColor; }
.met { color:var(--met); } .unmet { color:var(--unmet); } .unknown { color:var(--unknown); }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
@media (max-width:700px) { .grid { grid-template-columns:1fr; } }
.orig { background:var(--orig); border-radius:6px; padding:8px; }
.prop { background:var(--add); border-radius:6px; padding:8px; }
.label { font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; }
.excerpt { color:var(--muted); font-style:italic; }
.claim-text { white-space:pre-wrap; overflow-wrap:anywhere; }
ins { background:var(--add); text-decoration:underline; }
del { text-decoration:line-through; }
.checks { border-top:1px solid var(--line); margin-top:10px; padding-top:8px; }
table { width:100%; border-collapse:collapse; } td, th { text-align:left; padding:6px; border-bottom:1px solid var(--line); vertical-align:top; }
"""


def _word_changes(original: str, proposed: str) -> str:
    """Escaped word-level changes; this describes wording, never semantic truth."""
    before, after = original.split(), proposed.split()
    parts = []
    for tag, a, b, c, d in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if tag in ('delete', 'replace'):
            parts.append(f'<del>{_e(" ".join(before[a:b]))}</del>')
        if tag in ('insert', 'replace'):
            parts.append(f'<ins>{_e(" ".join(after[c:d]))}</ins>')
        if tag == 'equal':
            parts.append(_e(' '.join(after[c:d])))
    return ' '.join(parts)


def _claim_card(prof: dict, claim: dict, label: str, problems: list[str]) -> str:
    sources = profile_mod.sources(prof)
    cited = claim.get('sources') or []
    original = validate.originals(prof, cited)
    source_rows = []
    for sid in cited:
        source = sources.get(sid)
        if source:
            owner = sources.get(source.get('entry'), {}).get('text', '')
            source_rows.append(f'<li><b>{_e(sid)}</b> · {_e(owner or source["kind"])}'
                               f'<div class="claim-text">{_e(source["text"])}</div></li>')
        else:
            source_rows.append(f'<li class="unmet">{_e(sid)} — missing from current profile</li>')
    unchanged = len(cited) == 1 and validate.same_text(original, claim['text'])
    transformation = 'Unchanged wording' if unchanged else 'Reworded or combined sources'
    verdict = ('<b class="unmet">Checks need attention</b><ul>'
               + ''.join(f'<li>{_e(p)}</li>' for p in problems) + '</ul>') if problems else (
                   '<b>Current rule checks passed</b> · source references and detectable numbers, '
                   'technologies and credentials; not proof of meaning.')
    changes = '' if unchanged else (
        '<details><summary>Wording changes: deleted / added</summary>'
        f'<p>{_word_changes(original, claim["text"])}</p></details>')
    return (f'<article class="card"><div class="grid"><div class="orig"><div class="label">Current profile sources</div>'
            f'<ul>{"".join(source_rows) or "<li>No sources cited.</li>"}</ul></div>'
            f'<div class="prop"><div class="label">{_e(label)}</div><div class="claim-text">{_e(claim["text"])}</div></div></div>'
            f'<p>{transformation}</p>{changes}<div class="checks">{verdict}'
            '<p class="meta">Meaning, attribution and real-world accuracy are not checked automatically. '
            'Confirm that the sources support this exact claim, including your role and the outcome.</p></div></article>')


def _bullet_pairs(job: dict, prof: dict, resume: dict | None, heading: str) -> str:
    if not resume:
        return f"<h2>{_e(heading)}</h2><p class='meta'>None.</p>"
    sources = profile_mod.sources(prof)
    html = [f"<h2>{_e(heading)}</h2>"]
    try:
        _, warnings = validate.validate_proposal(prof, job, resume)
        problems = []
    except ResuError as exc:
        problems, warnings = exc.details or [str(exc)], []
    # Full validation includes entry ownership. An invalid resume has no passing cards.
    if warnings:
        html.append('<ul>' + ''.join(f'<li>{_e(w)}</li>' for w in warnings) + '</ul>')
    if resume.get("summary"):
        html.append(_claim_card(prof, resume['summary'], 'Summary', problems))
    for section in ("experience", "projects"):
        for item in resume.get(section) or []:
            entry = sources.get(item["entry"], {})
            html.append(f"<h3>{_e(entry.get('text', item['entry']))} <span class='meta'>({_e(item['entry'])})</span></h3>")
            for bullet in item["bullets"]:
                html.append(_claim_card(prof, bullet, 'Resume claim', problems))
    html.append(f"<p><b>Skills shown:</b> {_e(', '.join(resume.get('skills') or []))}</p>")
    return "".join(html)


def review_html(job: dict, prof: dict, pkg: dict, proposal: dict | None) -> str:
    results = checklist_mod.evaluate(job, prof)
    counts = checklist_mod.summary(results)
    state = package_mod.review_state(job, pkg, prof)
    rows = []
    for r in results:
        evidence = "<br>".join(f"{_e(e['id'])}: {_e(e['text'])}" for e in r["evidence"])
        rows.append(
            f"<tr><td><span class='pill {r['status']}'>{r['status'].upper()}</span></td>"
            f"<td><b>{_e(r['text'])}</b> <span class='meta'>({_e(r['importance'])})</span><br>"
            f"<span class='excerpt'>“{_e(r['excerpt'])}”</span></td><td>{_e(r['basis'])}{'<br>' + evidence if evidence else ''}</td></tr>"
        )
    answers = package_mod.resolved(job, prof, pkg)["answers"]
    answer_rows = []
    for a in answers:
        saved = pkg["answers"].get(a["id"]) or {}
        pending_answer = pkg["answer_proposals"].get(a["id"])
        shown = saved or pending_answer or {}
        question = next(q for q in job['questions'] if q['id'] == a['id'])
        def draft_card(record, label):
            problems = validate.validate_answer(prof, job, record['text'], record['sources'],
                                                question.get('limit'), question.get('limit_unit', 'chars'))
            refusal = package_mod._draft_refusal(question)
            if refusal:
                problems.append(refusal)
            return _claim_card(prof, record, label, problems)
        is_draft = bool(shown) and (shown.get('source') == 'ai_draft' or not saved)
        content = draft_card(shown, a['label']) if is_draft else (
            f'<div class="claim-text">{_e(a["text"])}</div>'
            '<p class="meta">Not an AI claim check: this value is from the user/profile, skipped, or still unresolved.</p>')
        draft = ""
        if saved and pending_answer:
            draft = draft_card(pending_answer, 'Replacement draft (pending review)')
        answer_rows.append(
            f"<tr><td>{_e(a['id'])}{' *' if a['required'] else ''}</td><td>{_e(a['question'])}</td>"
            f"<td><span class='pill {'met' if a['resolved'] else 'unknown'}'>{_e(a['label'])}</span><br>"
            f"{content}{draft}</td></tr>")
    answer_rows = "".join(answer_rows) or "<tr><td colspan=3 class='meta'>No questions added.</td></tr>"
    from . import letters
    letter_review = letters.review_section(pkg, job, prof)
    pending = proposal["proposal"] if proposal else None
    observation = listing.assess(job)
    listing_notes = ''.join(f'<li>{_e(w)}</li>' for w in observation['warnings'])
    body = f"""
<main>
<h1>{_e(job['title'])} — {_e(job['company'])}</h1>
<p class="meta">Job {_e(job['id'])} · review state <b>{_e(state.upper())}</b> · tracking <b>{_e(job['tracking']['status'])}</b> ·
profile r{prof['_meta']['revision']} · job r{job['revision']}</p>
<h2>Listing observation</h2>
<p>Listing: <b>{_e(observation['state'])}</b> · checked: {_e(observation['verified_at'] or 'unknown')} · deadline: {_e(observation['deadline'] or 'unknown')} · eligibility: {_e(observation['eligibility'])}</p>
<p>{_link(observation['source_url']) if observation['source_url'] else 'No verified source recorded.'}</p>
<ul>{listing_notes}</ul>
<p class="meta">An observation records what was read; it is not a live availability or eligibility guarantee.</p>
<h2>Requirement checklist</h2>
<p><span class="pill met">{counts['met']} met</span> <span class="pill unmet">{counts['unmet']} unmet</span>
<span class="pill unknown">{counts['unknown']} unknown</span></p>
<div class="card"><table><tr><th>Status</th><th>Requirement</th><th>Basis / evidence</th></tr>{''.join(rows) or '<tr><td colspan=3 class=meta>No requirements saved.</td></tr>'}</table></div>
<p class="meta">Sources below are from the current profile, not necessarily the version used to draft the text.
Rule checks run again for this review; they do not approve content or clear a stale approval.</p>
{_bullet_pairs(job, prof, pkg.get('resume'), 'Accepted resume')}
{_bullet_pairs(job, prof, pending, 'Latest proposal (not accepted)') if pending and pending != pkg.get('resume') else ''}
{letter_review}
<h2>Answers</h2>
<div class="card"><table><tr><th>ID</th><th>Question</th><th>Answer</th></tr>{answer_rows}</table></div>
<p class="meta">Automated checks catch invented numbers, technologies and credentials. They cannot judge meaning: read every proposed line against its original.</p>
</main>"""
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Review — {_e(job['company'])}</title><style>{_REVIEW_CSS}</style></head><body>{body}</body></html>"


# ---------------------------------------------------------------- output files and PDF

def out_dir(job_id: str) -> Path:
    path = store.job_dir(job_id) / "out"
    path.mkdir(exist_ok=True)
    return path


def pdf_name(prof: dict) -> str:
    return f"{slugify(prof['contact']['name'], 40).replace('-', '_').title()}_Resume.pdf"


def pdf_stamp(prof: dict, resume: dict, style: dict | None = None) -> dict:
    """What a resume PDF was printed from, so a snapshot can tell a current PDF from a stale one."""
    result = {"resume_hash": content_hash(resume), "profile_revision": prof["_meta"]["revision"]}
    settings = style_mod.normalize(style)
    if settings != style_mod.DEFAULT:
        result['style_hash'] = content_hash(settings)
    return result


def stamp_path(pdf: Path) -> Path:
    return pdf.with_name(pdf.name + ".json")


def find_browser() -> str | None:
    override = os.environ.get("RESUSKILL_BROWSER")
    if override:
        path = Path(override).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
        return shutil.which(override)
    candidates = []
    system = platform.system()
    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ]
    elif system == "Windows":
        for root in (os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", ""), os.environ.get("LOCALAPPDATA", "")):
            if not root:
                continue
            candidates += [
                os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
            ]
    for path in candidates:
        if Path(path).is_file() and os.access(path, os.X_OK):
            return path
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _pdf_complete(path: Path) -> bool:
    """Do not deliver a file while the browser is still writing its trailer."""
    try:
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                return False
            stream.seek(max(0, path.stat().st_size - 1024))
            return stream.read().rstrip().endswith(b"%%EOF")
    except FileNotFoundError:
        return False


def print_pdf(html_path: Path, pdf_path: Path) -> Path:
    browser = find_browser()
    if not browser:
        raise ResuError(
            "No Chrome, Chromium or Edge found for PDF output. Open the HTML file in a browser and use "
            "Print → Save as PDF, or set RESUSKILL_BROWSER to a Chromium-based browser."
        )
    # Print beside the destination and replace it only after successful output.
    # A failed browser run must not destroy the user's previous PDF.
    with tempfile.TemporaryDirectory(prefix="resuskill-browser-", dir=pdf_path.resolve().parent) as temp_dir:
        output = Path(temp_dir) / "resume.pdf"
        cmd = [
            browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--disable-background-networking", "--disable-component-update",
            "--no-pdf-header-footer", f"--user-data-dir={Path(temp_dir) / 'profile'}",
            f"--print-to-pdf={output}", html_path.resolve().as_uri(),
        ]
        # A temporary file avoids pipes held open by browser helpers. Read only a
        # bounded tail and report allow-listed diagnoses, never raw browser logs.
        with tempfile.TemporaryFile(mode="w+b") as diagnostics:
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=diagnostics)
            except OSError as exc:
                raise ResuError(
                    f"PDF browser could not start (OS error {exc.errno}). Check RESUSKILL_BROWSER and execution permissions. "
                    f"HTML is available at {html_path}; open it and use Print → Save as PDF."
                ) from exc
            timed_out, exit_code = False, None
            try:
                deadline, last_size = time.monotonic() + 90, -1
                while time.monotonic() < deadline:
                    exit_code = proc.poll()
                    if exit_code is not None:
                        break
                    size = output.stat().st_size if output.exists() else 0
                    if size and size == last_size and _pdf_complete(output):
                        break
                    last_size = size
                    time.sleep(0.5)
                else:
                    timed_out = True
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
            if not _pdf_complete(output):
                diagnostics.seek(0, os.SEEK_END)
                diagnostics.seek(max(0, diagnostics.tell() - 8192))
                tail = diagnostics.read(8192).decode("utf-8", errors="replace").lower()
                reason = "timed out after 90 seconds" if timed_out else f"exited with status {exit_code}"
                hint = "Check browser compatibility and execution permissions."
                if any(s in tail for s in ("operation not permitted", "permission denied", "sandbox")):
                    hint = "Browser logs indicate a possible permission or sandbox restriction. Use an environment that permits launching Chrome/Edge."
                elif any(s in tail for s in ("error while loading shared libraries", "library not loaded", "cannot open shared object")):
                    hint = "Browser logs indicate a missing system library. Repair the browser installation."
                raise ResuError(
                    f"The browser did not produce a complete PDF ({reason}). {hint} "
                    f"Existing PDFs were preserved. HTML: {html_path}. Open it and use Print → Save as PDF, "
                    "or run `doctor --pdf-smoke` to check the local browser."
                )
        os.replace(output, pdf_path)
    return pdf_path


def render(job_id: str, want_pdf: bool = False, use_proposal: bool = False, style: dict | None = None) -> dict:
    from . import jobs as jobs_mod

    job = jobs_mod.load(job_id)
    prof = profile_mod.load()
    pkg = package_mod.load(job_id)
    proposal = package_mod.load_proposal(job_id)
    selected = (proposal or {}).get('proposal') if use_proposal else pkg.get('resume')
    if use_proposal and not selected:
        raise ResuError("No resume proposal to preview")
    if selected:
        missing = _missing_refs(prof, selected)
        if missing:
            raise ResuError(f"Resume refers to entries no longer in the profile: {', '.join(missing)}. Propose a new draft.")
        selected, _ = validate.validate_proposal(prof, job, selected)
    # Preflight before touching old exports or invoking the PDF browser.
    folder = out_dir(job_id)
    settings = style_mod.normalize(style) if style is not None else style_mod.saved(folder)
    outputs: dict[str, str] = {}

    review = folder / "review.html"
    review.write_text(review_html(job, prof, pkg, proposal), encoding="utf-8")
    outputs["review"] = str(review)

    if use_proposal:
        if not proposal:
            raise ResuError("No resume proposal to preview")
        resume, target = selected, folder / "preview.html"
    else:
        if not pkg.get("resume"):
            outputs["note"] = "No accepted resume yet; only the review page was written. Use --proposal to preview."
            return outputs
        resume, target = selected, folder / "resume.html"
        state = package_mod.review_state(job, pkg, prof)
        if state != package_mod.APPROVED:
            outputs["note"] = f"Package is {state.upper()}; this resume has not been approved in its current form."
    target.write_text(resume_html(prof, resume, f"{prof['contact']['name']} — Resume", settings), encoding="utf-8")
    if style is not None:
        store.write_json(folder / 'style.json', settings)
    outputs["resume"] = str(target)
    if want_pdf:
        pdf = folder / (pdf_name(prof) if not use_proposal else "preview.pdf")
        outputs["pdf"] = str(print_pdf(target, pdf))
        stamp_path(pdf).unlink(missing_ok=True)
        if not use_proposal:
            store.write_json(stamp_path(pdf), pdf_stamp(prof, resume, settings))
    return outputs
