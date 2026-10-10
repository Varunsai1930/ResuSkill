"""Command-line interface. Every write to stored data goes through these commands."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from . import checklist as checklist_mod
from . import jobs as jobs_mod
from . import package as package_mod
from . import profile as profile_mod
from . import questions as q_mod
from . import render as render_mod
from . import store
from . import track as track_mod
from .util import ResuError


def out(data, as_json: bool, text: str | None = None) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif text is not None:
        print(text)


def bullets(lines) -> str:
    return "\n".join(f"  - {line}" for line in lines)


# ---------------------------------------------------------------- profile

def profile_text(prof: dict) -> str:
    c = prof["contact"]
    lines = [f"Profile r{prof['_meta']['revision']} (updated {prof['_meta']['updated_at']})",
             f"{c['name']} | {c.get('email') or '-'} | {c.get('phone') or '-'} | {c.get('location') or '-'}"]
    for label, url in (c.get("links") or {}).items():
        lines.append(f"  {label}: {url}")
    if prof.get("summary"):
        lines.append(f"[summary] {prof['summary']}")
    for section in profile_mod.ENTRY_SECTIONS:
        if not prof.get(section):
            continue
        lines.append(f"\n{section.upper()}")
        for e in prof[section]:
            head = " | ".join(str(e.get(f)) for f in ("title", "role", "organization", "name", "degree", "field", "institution") if e.get(f))
            dates = f"{e.get('start', '')} - {e.get('graduation') or e.get('end', '')}".strip(" -")
            tech = f" [{', '.join(e['technologies'])}]" if e.get("technologies") else ""
            lines.append(f"[{e['id']}] {head} ({dates}){tech}")
            lines.extend(f"    [{b['id']}] {b['text']}" for b in e.get("bullets") or [])
    lines.append("\nSKILLS: " + (", ".join(s["name"] for s in prof.get("skills") or []) or "-"))
    if prof.get("skills_absent"):
        lines.append("CONFIRMED NOT HELD: " + ", ".join(prof["skills_absent"]))
    for cert in prof.get("certifications") or []:
        lines.append(f"[{cert['id']}] {cert['name']} {cert.get('issuer', '')} {cert.get('date', '')}".rstrip())
    p, a = prof.get("preferences") or {}, prof.get("availability") or {}
    lines.append(f"PREFERENCES: roles={p.get('roles') or '-'} locations={p.get('locations') or '-'} work_mode={p.get('work_mode') or 'unknown'}")
    lines.append(f"AVAILABILITY: start={a.get('start_date') or 'unknown'} {a.get('notes') or ''}".rstrip())
    for auth in prof.get("authorization") or []:
        def fmt(v):
            return {True: "yes", False: "no", None: "unknown"}[v]
        lines.append(f"AUTHORIZATION {auth['country']}: authorized={fmt(auth['authorized'])} requires_sponsorship={fmt(auth['requires_sponsorship'])}")
    return "\n".join(lines)


def cmd_profile(args) -> None:
    if args.action == "template":
        print(json.dumps(profile_mod.TEMPLATE, indent=2))
    elif args.action == "show":
        prof = profile_mod.load()
        out(prof, args.json, profile_text(prof))
    elif args.action == "diff":
        current = profile_mod.load(required=False)
        new, warnings = profile_mod.normalize(store.load_input(args.file), current)
        changes = profile_mod.diff(current, new)
        out({"changes": changes, "warnings": warnings}, args.json,
            ("Proposed changes (not saved):\n" + bullets(changes) if changes else "No changes.")
            + (f"\nWarnings:\n{bullets(warnings)}" if warnings else ""))
    elif args.action == "save":
        prof, changes, warnings = profile_mod.save(store.load_input(args.file))
        text = f"Saved profile r{prof['_meta']['revision']}:\n{bullets(changes)}" if changes else "No changes; profile unchanged."
        out({"revision": prof["_meta"]["revision"], "changes": changes, "warnings": warnings}, args.json,
            text + (f"\nWarnings:\n{bullets(warnings)}" if warnings else ""))


# ---------------------------------------------------------------- jobs and checklist

def job_text(job: dict) -> str:
    lines = [f"{job['id']}: {job['title']} at {job['company']} (r{job['revision']})",
             f"Location: {job.get('location') or '-'} | URL: {job.get('url') or '-'}",
             f"Status: {job['tracking']['status']} | Description: {len(job['description'])} characters"]
    if job["requirements"]:
        lines.append("Requirements:")
        for r in job["requirements"]:
            crit = f" {json.dumps(r['criterion'])}" if r["criterion"] else ""
            lines.append(f"  [{r['id']}] ({r['importance']}, {r['category']}) {r['text']}{crit}")
    else:
        lines.append("Requirements: none saved yet")
    if job.get("questions"):
        lines.append("Questions:")
        lines.extend(f"  [{q['id']}] ({q['category']}{', required' if q['required'] else ''}) {q['text']}" for q in job["questions"])
    for note in job["tracking"].get("notes") or []:
        lines.append(f"Note {note['at'][:10]}: {note['text']}")
    return "\n".join(lines)


def cmd_job(args) -> None:
    if args.action == "add":
        description = store.load_text(args.description_file)
        job = jobs_mod.add(args.company, args.title, description, args.location or "", args.url or "")
        out(job, args.json, f"Saved job {job['id']}. Next: extract requirements and run `job requirements {job['id']} --file ...`.")
    elif args.action == "show":
        job = jobs_mod.load(args.job)
        if args.description:
            print(job["description"])
            return
        out(job, args.json, job_text(job))
    elif args.action == "requirements":
        job = jobs_mod.set_requirements(args.job, store.load_input(args.file))
        out(job["requirements"], args.json, f"Saved {len(job['requirements'])} requirements (job r{job['revision']}).")


def cmd_jobs(args) -> None:
    table = track_mod.rows()
    if args.json or not table:
        out(table, args.json, "No jobs saved yet.")
        return
    print(f"{'JOB':34} {'COMPANY':18} {'TITLE':26} {'REVIEW':9} {'STATUS':11} {'CHECKLIST':16} UPDATED")
    for r in table:
        counts = r["checklist"]
        check = f"{counts['met']}M {counts['unmet']}U {counts['unknown']}?" if counts else "-"
        print(f"{r['id'][:34]:34} {r['company'][:18]:18} {r['title'][:26]:26} {r['review']:9} {r['status']:11} {check:16} {r['updated']}")


def checklist_text(results: list[dict]) -> str:
    counts = checklist_mod.summary(results)
    lines = [f"Met {counts['met']} | Unmet {counts['unmet']} (required: {counts['required_unmet']}) | Unknown {counts['unknown']}"]
    for status in checklist_mod.STATUSES:
        group = [r for r in results if r["status"] == status]
        if not group:
            continue
        lines.append(f"\n{status.upper()}")
        for r in group:
            lines.append(f"  [{r['id']}] ({r['importance']}) {r['text']}")
            lines.append(f"      basis: {r['basis']}")
            lines.extend(f"      evidence {e['id']}: {e['text']}" for e in r["evidence"])
            if r["stale_links"]:
                lines.append(f"      removed sources: {', '.join(r['stale_links'])}")
            lines.append(f"      quote: \"{r['excerpt']}\"")
    return "\n".join(lines)


def cmd_checklist(args) -> None:
    job = jobs_mod.load(args.job)
    if not job["requirements"]:
        raise ResuError("No requirements saved for this job yet")
    results = checklist_mod.evaluate(job, profile_mod.load())
    out({"summary": checklist_mod.summary(results), "results": results}, args.json, checklist_text(results))


def cmd_evidence(args) -> None:
    if args.action == "link":
        job = checklist_mod.link(args.job, args.req, args.sources)
        print(f"Linked {', '.join(job['evidence'][args.req]['sources'])} to {args.req}.")
    else:
        checklist_mod.unlink(args.job, args.req)
        print(f"Removed evidence links from {args.req}.")


def cmd_override(args) -> None:
    checklist_mod.override(args.job, args.req, args.status, args.reason or "")
    print(f"Override for {args.req}: {args.status}.")


# ---------------------------------------------------------------- resume

def resume_text(resume: dict) -> str:
    lines = []
    if resume.get("summary"):
        lines.append(f"SUMMARY: {resume['summary']['text']}  <- {', '.join(resume['summary']['sources'])}")
    for section in ("experience", "projects"):
        for item in resume.get(section) or []:
            lines.append(f"[{item['entry']}]")
            lines.extend(f"  - {b['text']}  <- {', '.join(b['sources'])}" for b in item["bullets"])
    lines.append(f"EDUCATION: {', '.join(resume.get('education') or []) or '-'}")
    lines.append(f"SKILLS: {', '.join(resume.get('skills') or []) or '-'}")
    return "\n".join(lines)


def cmd_resume(args) -> None:
    if args.action == "propose":
        record, warnings = package_mod.propose_resume(args.job, store.load_input(args.file), args.model or "")
        out(record, args.json, "Proposal passed validation and was stored (not accepted).\n"
            + resume_text(record["proposal"])
            + (f"\nWarnings:\n{bullets(warnings)}" if warnings else "")
            + f"\nShow the user `render {args.job} --proposal` / review.html, then `resume accept {args.job}` after they approve.")
    elif args.action == "accept":
        package_mod.accept_resume(args.job)
        print("Accepted the current proposal as the package resume. Approval (if any) was cleared.")
    elif args.action == "show":
        if args.proposal:
            record = package_mod.load_proposal(args.job)
            if not record:
                raise ResuError("No proposal stored")
            out(record, args.json, resume_text(record["proposal"]))
        else:
            resume = package_mod.load(args.job).get("resume")
            if not resume:
                raise ResuError("No accepted resume yet")
            out(resume, args.json, resume_text(resume))


# ---------------------------------------------------------------- questions and answers

def answers_text(job: dict, prof: dict, pkg: dict) -> str:
    items = package_mod.resolved(job, prof, pkg)["answers"]
    if not items:
        return "No questions added."
    lines = []
    for a in items:
        lines.append(f"[{a['id']}] ({a['category']}{', required' if a['required'] else ''}) {a['question']}")
        lines.append(f"    {a['label']}: {a['text'] or '-'}")
    return "\n".join(lines)


def cmd_questions(args) -> None:
    if args.action == "add":
        question = package_mod.add_question(args.job, args.text, not args.optional, args.limit, args.unit, args.category)
        hint = {
            q_mod.FACTUAL: "answered from the profile",
            q_mod.SENSITIVE_FACTUAL: "profile value needs explicit user confirmation (`answers confirm`)",
            q_mod.SENSITIVE: "the user must answer it themselves (`answers set`) or skip if optional",
            q_mod.OPEN: "draft an answer with sources (`answers propose`)",
            q_mod.UNKNOWN: "ask the user for its category (`questions categorize`)",
        }[question["category"]]
        out(question, args.json, f"Added {question['id']} as {question['category']}: {hint}.")
    elif args.action == "list":
        job = jobs_mod.load(args.job)
        prof = profile_mod.load()
        pkg = package_mod.load(args.job)
        out(package_mod.resolved(job, prof, pkg)["answers"], args.json, answers_text(job, prof, pkg))
    elif args.action == "categorize":
        question = package_mod.set_category(args.job, args.qid, args.category)
        print(f"{question['id']} is now {question['category']}.")
    elif args.action == "remove":
        package_mod.remove_question(args.job, args.qid)
        print(f"Removed {args.qid}.")


def cmd_answers(args) -> None:
    if args.action == "propose":
        staged = package_mod.propose_answers(args.job, store.load_input(args.file), args.model or "")
        print(f"Stored drafts for {', '.join(staged)} (pending review). Accept with `answers accept {args.job} <ids>`.")
    elif args.action == "accept":
        accepted = package_mod.accept_answers(args.job, args.qids)
        print(f"Accepted {', '.join(accepted)}. Approval (if any) was cleared.")
    elif args.action == "set":
        text = store.load_text(args.file) if args.file else args.text
        package_mod.set_answer(args.job, args.qid, text, skip=args.skip)
        print(f"Saved the user's answer for {args.qid}." if not args.skip else f"Marked {args.qid} as skipped.")
    elif args.action == "confirm":
        answer = package_mod.confirm_answer(args.job, args.qid)
        print(f"Confirmed {args.qid}: {answer['text']}")


def cmd_bank(args) -> None:
    if args.action == "save":
        entry = package_mod.bank_save(args.job, args.qid)
        print(f"Saved to answer bank as {entry['id']}.")
    else:
        items = q_mod.bank()
        out(items, args.json, "\n".join(f"[{i['id']}] {i['question']}\n    {i['text']}" for i in items) or "Answer bank is empty.")


# ---------------------------------------------------------------- package, render, tracking

def cmd_package(args) -> None:
    if args.action == "check":
        blockers, warnings = package_mod.check(args.job)
        job = jobs_mod.load(args.job)
        state = package_mod.review_state(job, package_mod.load(args.job), profile_mod.load())
        text = f"Review state: {state.upper()}\n"
        text += f"Blockers:\n{bullets(blockers)}\n" if blockers else "No blockers: ready for the user to approve.\n"
        text += f"Warnings:\n{bullets(warnings)}" if warnings else ""
        out({"state": state, "blockers": blockers, "warnings": warnings}, args.json, text.rstrip())
        return 1 if blockers else 0
    elif args.action == "approve":
        pkg = package_mod.approve(args.job)
        print(f"Package approved (hash {pkg['approval']['hash']}). This does not mark it Applied.")


def cmd_render(args) -> None:
    outputs = render_mod.render(args.job, want_pdf=args.pdf, use_proposal=args.proposal)
    out(outputs, args.json, "\n".join(f"{k}: {v}" for k, v in outputs.items()))


def cmd_track(args) -> None:
    job = track_mod.set_status(args.job, args.status, args.note or "")
    snap = f" Snapshot: {job['tracking']['snapshot']}." if args.status == "applied" else ""
    print(f"{job['id']} is now {job['tracking']['status']}.{snap}")


def cmd_note(args) -> None:
    track_mod.add_note(args.job, args.text)
    print("Note saved.")


def cmd_status(args) -> None:
    prof = profile_mod.load(required=False)
    table = track_mod.rows()
    info = {
        "version": __version__,
        "data_dir": str(store.home()),
        "profile_revision": prof["_meta"]["revision"] if prof else None,
        "jobs": len(table),
        "pdf_browser": render_mod.find_browser(),
    }
    out(info, args.json, "\n".join(f"{k}: {v}" for k, v in info.items()))


def cmd_demo(args) -> None:
    from .demo import create

    result = create(args.output)
    out(result, args.json, "\n".join(f"{k}: {v}" for k, v in result.items()))


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="resuskill", description="ResuSkill: evidence-backed job application packages.")
    parser.add_argument("--version", action="version", version=f"resuskill {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", parents=[common], help="data directory, profile revision, job count")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("demo", parents=[common], help="create a fictional draft in a separate directory")
    p.add_argument("--output", help="new directory (defaults to a fresh temporary directory)")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("profile", help="canonical candidate profile")
    ps = p.add_subparsers(dest="action", required=True)
    ps.add_parser("template", parents=[common], help="print an empty profile skeleton")
    ps.add_parser("show", parents=[common], help="show the profile with IDs")
    for name, desc in (("diff", "preview changes without saving"), ("save", "validate and save (after user confirmation)")):
        x = ps.add_parser(name, parents=[common], help=desc)
        x.add_argument("--file", required=True, help="profile JSON file, or - for stdin")
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("job", help="saved jobs")
    js = p.add_subparsers(dest="action", required=True)
    x = js.add_parser("add", parents=[common], help="save a job description")
    x.add_argument("--company", required=True)
    x.add_argument("--title", required=True)
    x.add_argument("--description-file", required=True, help="text file with the pasted description, or -")
    x.add_argument("--location")
    x.add_argument("--url")
    x = js.add_parser("show", parents=[common])
    x.add_argument("job")
    x.add_argument("--description", action="store_true", help="print the full description text")
    x = js.add_parser("requirements", parents=[common], help="save reviewed requirements (all-or-nothing)")
    x.add_argument("job")
    x.add_argument("--file", required=True)
    p.set_defaults(func=cmd_job)

    p = sub.add_parser("jobs", parents=[common], help="tracker table of all jobs")
    p.set_defaults(func=cmd_jobs)

    p = sub.add_parser("checklist", parents=[common], help="deterministic requirement checklist")
    p.add_argument("job")
    p.set_defaults(func=cmd_checklist)

    p = sub.add_parser("evidence", help="user-confirmed evidence links")
    es = p.add_subparsers(dest="action", required=True)
    x = es.add_parser("link")
    x.add_argument("job")
    x.add_argument("req")
    x.add_argument("sources", nargs="+", help="profile source IDs (entries or bullets)")
    x = es.add_parser("unlink")
    x.add_argument("job")
    x.add_argument("req")
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser("override", help="user correction of a checklist result")
    p.add_argument("job")
    p.add_argument("req")
    p.add_argument("--status", required=True, choices=["met", "unmet", "unknown", "clear"])
    p.add_argument("--reason")
    p.set_defaults(func=cmd_override)

    p = sub.add_parser("resume", help="tailored resume proposals")
    rs = p.add_subparsers(dest="action", required=True)
    x = rs.add_parser("propose", parents=[common], help="validate and store a proposal")
    x.add_argument("job")
    x.add_argument("--file", required=True)
    x.add_argument("--model", help="model name, recorded for traceability")
    x = rs.add_parser("accept", parents=[common], help="make the stored proposal the accepted resume")
    x.add_argument("job")
    x = rs.add_parser("show", parents=[common])
    x.add_argument("job")
    x.add_argument("--proposal", action="store_true")
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("questions", help="application questions")
    qs = p.add_subparsers(dest="action", required=True)
    x = qs.add_parser("add", parents=[common])
    x.add_argument("job")
    x.add_argument("--text", required=True)
    x.add_argument("--optional", action="store_true", help="question is not required")
    x.add_argument("--limit", type=int)
    x.add_argument("--unit", default="chars", choices=["chars", "words"])
    x.add_argument("--category", choices=list(q_mod.CATEGORIES), help="override the detected category")
    x = qs.add_parser("list", parents=[common])
    x.add_argument("job")
    x = qs.add_parser("categorize", parents=[common])
    x.add_argument("job")
    x.add_argument("qid")
    x.add_argument("category", choices=[q_mod.FACTUAL, q_mod.SENSITIVE_FACTUAL, q_mod.SENSITIVE, q_mod.OPEN])
    x = qs.add_parser("remove", parents=[common])
    x.add_argument("job")
    x.add_argument("qid")
    p.set_defaults(func=cmd_questions)

    p = sub.add_parser("answers", help="answers to application questions")
    an = p.add_subparsers(dest="action", required=True)
    x = an.add_parser("propose", parents=[common], help="store AI drafts for open questions")
    x.add_argument("job")
    x.add_argument("--file", required=True)
    x.add_argument("--model")
    x = an.add_parser("accept", parents=[common], help="accept pending drafts (all if no IDs)")
    x.add_argument("job")
    x.add_argument("qids", nargs="*")
    x = an.add_parser("set", parents=[common], help="store the user's own answer")
    x.add_argument("job")
    x.add_argument("qid")
    g = x.add_mutually_exclusive_group(required=True)
    g.add_argument("--text")
    g.add_argument("--file")
    g.add_argument("--skip", action="store_true", help="explicitly leave an optional question blank")
    x = an.add_parser("confirm", parents=[common], help="user confirms the profile value")
    x.add_argument("job")
    x.add_argument("qid")
    p.set_defaults(func=cmd_answers)

    p = sub.add_parser("bank", help="reusable answer bank")
    bs = p.add_subparsers(dest="action", required=True)
    x = bs.add_parser("save", parents=[common])
    x.add_argument("job")
    x.add_argument("qid")
    bs.add_parser("list", parents=[common])
    p.set_defaults(func=cmd_bank)

    p = sub.add_parser("package", help="review and approval")
    pk = p.add_subparsers(dest="action", required=True)
    for name in ("check", "approve"):
        x = pk.add_parser(name, parents=[common])
        x.add_argument("job")
    p.set_defaults(func=cmd_package)

    p = sub.add_parser("render", parents=[common], help="write resume.html, review.html and optionally a PDF")
    p.add_argument("job")
    p.add_argument("--pdf", action="store_true")
    p.add_argument("--proposal", action="store_true", help="preview the pending proposal instead")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("track", help="set tracking status (applied freezes a snapshot)")
    p.add_argument("job")
    p.add_argument("status", choices=jobs_mod.STATUSES)
    p.add_argument("--note")
    p.set_defaults(func=cmd_track)

    p = sub.add_parser("note", help="add a tracking note")
    p.add_argument("job")
    p.add_argument("text")
    p.set_defaults(func=cmd_note)
    return parser


def main(argv=None) -> int:
    # Output carries names and job text in any script; don't depend on the console code page.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "json"):
        args.json = False
    try:
        result = args.func(args)
    except ResuError as exc:
        print(f"error: {exc}", file=sys.stderr)
        for detail in exc.details:
            print(f"  - {detail}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError) as exc:
        print(f"error: could not read or write the requested file: {exc}", file=sys.stderr)
        return 1
    return result if isinstance(result, int) else 0
