"""Render the resume and the review page as HTML, and optionally print the resume to PDF.

Names, employers, titles, dates, degrees and contact details always come from the
profile. Only bullet text, summary text, ordering and skill selection come from the
validated package. Every value is HTML-escaped.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from html import escape
from pathlib import Path
from string import Template

from . import checklist as checklist_mod
from . import package as package_mod
from . import profile as profile_mod
from . import store, validate
from .skills import canon
from .util import ResuError, slugify

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


def _link(url: str) -> str:
    href = url if url.startswith(("http://", "https://", "mailto:")) else f"https://{url}"
    shown = url.replace("https://", "").replace("http://", "").rstrip("/")
    return f'<a href="{_e(href)}">{_e(shown)}</a>'


def _row(what: str, when: str) -> str:
    return f'<div class="row"><span class="what">{what}</span><span class="when">{_e(when)}</span></div>'


def resume_body(prof: dict, resume: dict) -> str:
    contact = prof["contact"]
    bits = [f"<span>{_e(contact.get(k))}</span>" for k in ("location", "phone") if contact.get(k)]
    if contact.get("email"):
        bits.insert(0, f'<span><a href="mailto:{_e(contact["email"])}">{_e(contact["email"])}</a></span>')
    bits += [f"<span>{_link(url)}</span>" for url in (contact.get("links") or {}).values() if url]
    html = [f'<header><h1>{_e(contact["name"])}</h1><div class="contact">{"".join(bits)}</div></header>']

    if resume.get("summary"):
        html.append(f'<section><h2>Summary</h2><p class="summary">{_e(resume["summary"]["text"])}</p></section>')

    education = {e["id"]: e for e in prof.get("education") or []}
    if resume.get("education"):
        parts = []
        for edu_id in resume["education"]:
            edu = education[edu_id]
            degree = ", ".join(x for x in (edu.get("degree"), edu.get("field")) if x)
            sub = " • ".join(x for x in (degree, f"GPA {edu['gpa']}" if edu.get("gpa") else "") if x)
            bullets = "".join(f"<li>{_e(b['text'])}</li>" for b in edu.get("bullets") or [])
            parts.append(
                f'<div class="entry">{_row(_e(edu["institution"]), date_range(edu))}'
                f'<div class="sub">{_e(sub)}</div>{f"<ul>{bullets}</ul>" if bullets else ""}</div>'
            )
        html.append(f"<section><h2>Education</h2>{''.join(parts)}</section>")

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
        html.append(f"<section><h2>{heading}</h2>{''.join(parts)}</section>")

    if resume.get("skills"):
        categories: dict[str, list[str]] = {}
        lookup = {canon(s["name"]): s.get("category") or "Skills" for s in prof.get("skills") or []}
        for name in resume["skills"]:
            categories.setdefault(lookup.get(canon(name), "Skills"), []).append(name)
        rows = "".join(f"<p><b>{_e(cat)}:</b> {_e(', '.join(names))}</p>" for cat, names in categories.items())
        html.append(f'<section class="skills"><h2>Skills</h2>{rows}</section>')

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
        html.append(f"<section><h2>Certifications</h2><ul>{items}</ul></section>")
    return "\n".join(html)


def resume_html(prof: dict, resume: dict, title: str) -> str:
    template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    return template.safe_substitute(title=_e(title), body=resume_body(prof, resume))


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
table { width:100%; border-collapse:collapse; } td, th { text-align:left; padding:6px; border-bottom:1px solid var(--line); vertical-align:top; }
"""


def _bullet_pairs(prof: dict, resume: dict | None, heading: str) -> str:
    if not resume:
        return f"<h2>{_e(heading)}</h2><p class='meta'>None.</p>"
    sources = profile_mod.sources(prof)
    html = [f"<h2>{_e(heading)}</h2>"]
    if resume.get("summary"):
        html.append(
            f"<div class='card grid'><div class='orig'><div class='label'>Sources</div>{_e(validate.originals(prof, resume['summary']['sources']))}</div>"
            f"<div class='prop'><div class='label'>Summary</div>{_e(resume['summary']['text'])}</div></div>"
        )
    for section in ("experience", "projects"):
        for item in resume.get(section) or []:
            entry = sources.get(item["entry"], {})
            html.append(f"<h3>{_e(entry.get('text', item['entry']))} <span class='meta'>({_e(item['entry'])})</span></h3>")
            for bullet in item["bullets"]:
                original = validate.originals(prof, bullet["sources"])
                same = " <span class='meta'>(unchanged)</span>" if validate.same_text(original, bullet["text"]) else ""
                html.append(
                    f"<div class='card grid'><div class='orig'><div class='label'>Original · {_e(', '.join(bullet['sources']))}</div>{_e(original)}</div>"
                    f"<div class='prop'><div class='label'>Proposed{same}</div>{_e(bullet['text'])}</div></div>"
                )
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
    answer_rows = "".join(
        f"<tr><td>{_e(a['id'])}{' *' if a['required'] else ''}</td><td>{_e(a['question'])}</td>"
        f"<td><span class='pill {'met' if a['resolved'] else 'unknown'}'>{_e(a['label'])}</span><br>{_e(a['text'])}</td></tr>"
        for a in answers
    ) or "<tr><td colspan=3 class='meta'>No questions added.</td></tr>"
    pending = proposal["proposal"] if proposal else None
    body = f"""
<main>
<h1>{_e(job['title'])} — {_e(job['company'])}</h1>
<p class="meta">Job {_e(job['id'])} · review state <b>{_e(state.upper())}</b> · tracking <b>{_e(job['tracking']['status'])}</b> ·
profile r{prof['_meta']['revision']} · job r{job['revision']}</p>
<h2>Requirement checklist</h2>
<p><span class="pill met">{counts['met']} met</span> <span class="pill unmet">{counts['unmet']} unmet</span>
<span class="pill unknown">{counts['unknown']} unknown</span></p>
<div class="card"><table><tr><th>Status</th><th>Requirement</th><th>Basis / evidence</th></tr>{''.join(rows) or '<tr><td colspan=3 class=meta>No requirements saved.</td></tr>'}</table></div>
{_bullet_pairs(prof, pkg.get('resume'), 'Accepted resume')}
{_bullet_pairs(prof, pending, 'Latest proposal (not accepted)') if pending and pending != pkg.get('resume') else ''}
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


def find_browser() -> str | None:
    override = os.environ.get("RESUSKILL_BROWSER")
    if override:
        return override if Path(override).exists() or shutil.which(override) else None
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
            candidates += [
                os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
            ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def print_pdf(html_path: Path, pdf_path: Path) -> Path:
    browser = find_browser()
    if not browser:
        raise ResuError(
            "No Chrome, Chromium or Edge found for PDF output. Open the HTML file in a browser and use "
            "Print → Save as PDF, or set RESUSKILL_BROWSER to a Chromium-based browser."
        )
    with tempfile.TemporaryDirectory(prefix="resuskill-browser-") as profile_dir:
        cmd = [
            browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            "--no-pdf-header-footer", f"--user-data-dir={profile_dir}",
            f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri(),
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=90, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ResuError("PDF printing timed out; use the browser's Save as PDF instead") from exc
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise ResuError("The browser did not produce a PDF; use the browser's Save as PDF instead")
    return pdf_path


def render(job_id: str, want_pdf: bool = False, use_proposal: bool = False) -> dict:
    from . import jobs as jobs_mod

    job = jobs_mod.load(job_id)
    prof = profile_mod.load()
    pkg = package_mod.load(job_id)
    proposal = package_mod.load_proposal(job_id)
    folder = out_dir(job_id)
    outputs: dict[str, str] = {}

    review = folder / "review.html"
    review.write_text(review_html(job, prof, pkg, proposal), encoding="utf-8")
    outputs["review"] = str(review)

    if use_proposal:
        if not proposal:
            raise ResuError("No resume proposal to preview")
        resume, target = proposal["proposal"], folder / "preview.html"
    else:
        if not pkg.get("resume"):
            outputs["note"] = "No accepted resume yet; only the review page was written. Use --proposal to preview."
            return outputs
        resume, target = pkg["resume"], folder / "resume.html"
    target.write_text(resume_html(prof, resume, f"{prof['contact']['name']} — Resume"), encoding="utf-8")
    outputs["resume"] = str(target)
    if want_pdf:
        outputs["pdf"] = str(print_pdf(target, folder / (pdf_name(prof) if not use_proposal else "preview.pdf")))
    return outputs
