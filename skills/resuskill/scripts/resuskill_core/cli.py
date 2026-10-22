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
from . import repos as repos_mod
from . import search as search_mod
from . import store
from . import track as track_mod
from . import listing as listing_mod
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
    elif args.action == "search-terms":
        result = search_mod.terms(args.role, args.location, args.max_queries, args.skill, args.level)
        out(result, args.json, search_text(result))


def search_text(result: dict) -> str:
    skills = ", ".join(f"{s['name']} ({s['evidence_count']})" for s in result["skills"]) or "-"
    level = result["level"]
    lines = [f"Roles ({result['role_source']}): {', '.join(result['roles']) or '-'}",
             f"Skills (entries using each): {skills}",
             f"In focused queries: {', '.join(result['query_skills']) or '-'}",
             f"Locations: {', '.join(result['locations']) or '-'} | work_mode: {result['work_mode'] or 'unknown'}",
             f"Level: {level['hint'] or 'unknown'} ({level['basis']})"]
    if result["skills_absent"]:
        lines.append(f"Confirmed not held: {', '.join(result['skills_absent'])}")
    if result["sponsorship_needed"]:
        lines.append(f"Needs sponsorship in: {', '.join(result['sponsorship_needed'])}")
    if result["authorization_unknown"]:
        lines.append(f"Authorization unknown for: {', '.join(result['authorization_unknown'])}")
    lines.append("Queries:\n" + (bullets(result["queries"]) if result["queries"] else "  (none)"))
    if result["warnings"]:
        lines.append(f"Warnings:\n{bullets(result['warnings'])}")
    return "\n".join(lines)


# ---------------------------------------------------------------- jobs and checklist

def job_text(job: dict) -> str:
    lines = [f"{job['id']}: {job['title']} at {job['company']} (r{job['revision']})",
             f"Location: {job.get('location') or '-'} | URL: {job.get('url') or '-'}",
             f"Status: {job['tracking']['status']} | Description: {len(job['description'])} characters"]
    listing = listing_mod.assess(job)
    lines.append(f"Listing: {listing['state']} | checked: {listing['verified_at'] or 'unknown'} | deadline: {listing['deadline'] or 'unknown'} | eligibility: {listing['eligibility']}")
    lines.extend('  ' + warning for warning in listing['warnings'])
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
            out(job["description"], args.json, job["description"])
            return
        out(job, args.json, job_text(job))
    elif args.action == "observe":
        job = jobs_mod.observe(args.job, store.load_input(args.file))
        out(listing_mod.assess(job), args.json, job_text(job))
    elif args.action == "requirements":
        job = jobs_mod.set_requirements(args.job, store.load_input(args.file))
        out(job["requirements"], args.json, f"Saved {len(job['requirements'])} requirements (job r{job['revision']}).")
    elif args.action == "repos":
        result = repos_mod.rank(args.job, store.load_input(args.file))
        out(result, args.json, repos_text(result))


def repos_text(result: dict) -> str:
    lines = ["Repository suggestions from metadata and README mentions (not saved; verify code and confirm projects before adding them):"]
    for c in result["candidates"]:
        where = f"already in profile as {c['in_profile']}" if c["in_profile"] else "not in profile"
        lines.append(f"  [{c['score']}] {c['name']} ({where}) {c['url']}")
        lines.append(f"      matches job: {', '.join(c['matches_job']) or '-'}; other: {', '.join(c['other_technologies']) or '-'}")
        if c["readme_mentions_job"] or c["other_readme_mentions"]:
            lines.append(f"      README mentions (check context): job {', '.join(c['readme_mentions_job']) or '-'}; "
                         f"other {', '.join(c['other_readme_mentions']) or '-'}")
        if c["description"]:
            lines.append(f"      description: {c['description']}")
        if c["notes"]:
            lines.append(f"      notes: {'; '.join(c['notes'])}")
    if not result["candidates"]:
        lines.append("  (none)")
    for e in result["excluded"]:
        lines.append(f"  excluded {e['name']}: {e['reason']}")
    if result["warnings"]:
        lines.append(f"Warnings:\n{bullets(result['warnings'])}")
    return "\n".join(lines)


def cmd_jobs(args) -> None:
    table = track_mod.rows()
    if args.json or not table:
        out(table, args.json, "No jobs saved yet.")
        return
    print(f"{'JOB':34} {'COMPANY':18} {'TITLE':26} {'REVIEW':9} {'STATUS':11} {'LISTING':14} {'CHECKLIST':16} UPDATED")
    for r in table:
        counts = r["checklist"]
        check = f"{counts['met']}M {counts['unmet']}U {counts['unknown']}?" if counts else "-"
        print(f"{r['id'][:34]:34} {r['company'][:18]:18} {r['title'][:26]:26} {r['review']:9} {r['status']:11} {r.get('listing', {}).get('state', '-'):14} {check:16} {r['updated']}")
        if r.get('listing'):
            info = r['listing']
            print(f"  deadline: {info['deadline'] or 'unknown'} | eligibility: {info['eligibility']}")
            for warning in info['warnings']:
                print('  ' + warning)
    for r in table:
        if r.get("error"):
            print(f"warning: {r['id']}: {r['error']}", file=sys.stderr)


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
        pkg = package_mod.accept_resume(args.job)
        out(pkg, args.json, "Accepted the current proposal as the package resume. Approval (if any) was cleared.")
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
        out(question, args.json, f"{question['id']} is now {question['category']}.")
    elif args.action == "remove":
        package_mod.remove_question(args.job, args.qid)
        out({"removed": args.qid}, args.json, f"Removed {args.qid}.")


def cmd_answers(args) -> None:
    if args.action == "propose":
        staged = package_mod.propose_answers(args.job, store.load_input(args.file), args.model or "")
        out({"staged": staged}, args.json,
            f"Stored drafts for {', '.join(staged)} (pending review). Accept with `answers accept {args.job} <ids>`.")
    elif args.action == "accept":
        accepted = package_mod.accept_answers(args.job, args.qids)
        out({"accepted": accepted}, args.json, f"Accepted {', '.join(accepted)}. Approval (if any) was cleared.")
    elif args.action == "set":
        text = store.load_text(args.file) if args.file else args.text
        answer = package_mod.set_answer(args.job, args.qid, text, skip=args.skip)
        out(answer, args.json,
            f"Saved the user's answer for {args.qid}." if not args.skip else f"Marked {args.qid} as skipped.")
    elif args.action == "confirm":
        answer = package_mod.confirm_answer(args.job, args.qid)
        out(answer, args.json, f"Confirmed {args.qid}: {answer['text']}")


def cmd_bank(args) -> None:
    if args.action == "save":
        entry = package_mod.bank_save(args.job, args.qid)
        out(entry, args.json, f"Saved to answer bank as {entry['id']}.")
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
        out(pkg, args.json, f"Package approved (hash {pkg['approval']['hash']}). This does not mark it Applied.")


def cmd_render(args) -> None:
    outputs = render_mod.render(args.job, want_pdf=args.pdf, use_proposal=args.proposal,
                                style=store.load_input(args.style) if args.style else None)
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

def cmd_doctor(args) -> int:
    from .doctor import check

    result = check(args.pdf_smoke)
    out(result, args.json, "\n".join(f"{c['status'].upper()}: {c['name']}: {c['detail']}" for c in result["checks"]))
    return 0 if result["ready"] else 1

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="resuskill", description="ResuSkill: evidence-backed job application packages.")
    parser.add_argument("--version", action="version", version=f"resuskill {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", parents=[common], help="data directory, profile revision, job count")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("doctor", parents=[common], help="check local setup without changing candidate data")
    p.add_argument("--pdf-smoke", action="store_true", help="also launch the local browser with fictional content")
    p.set_defaults(func=cmd_doctor)

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
    x = ps.add_parser("search-terms", parents=[common], help="job-search queries from the profile (offline)")
    x.add_argument("--role", action="append", help="target role from the user's request (repeatable)")
    x.add_argument("--location", action="append", help="location to search (repeatable)")
    x.add_argument("--skill", action="append", help="confirmed profile skill to put in queries (repeatable; default: top 2; broader queries also omit skills)")
    x.add_argument("--level", choices=search_mod.LEVELS, help="desired career level for roles without one; any omits level filters")
    x.add_argument("--max-queries", type=int, default=6)
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
    x = js.add_parser("observe", parents=[common], help="record reviewed listing status, dates and eligibility (offline)")
    x.add_argument("job")
    x.add_argument("--file", required=True)
    x = js.add_parser("repos", parents=[common], help="rank fetched GitHub repositories against the job (offline)")
    x.add_argument("job")
    x.add_argument("--file", required=True, help="GitHub /users/<name>/repos JSON, optionally with readme/languages added, or -")
    p.set_defaults(func=cmd_job)

    p = sub.add_parser("jobs", parents=[common], help="tracker table of all jobs")
    p.set_defaults(func=cmd_jobs)
    imp = p.add_subparsers(dest='action')
    x = imp.add_parser('import-preview', parents=[common])
    x.add_argument('--file', required=True)
    x.set_defaults(func=cmd_import)
    x = imp.add_parser('import-apply', parents=[common])
    x.add_argument('--file', required=True)
    x.add_argument('--preview', required=True)
    x.add_argument('--select', type=int, nargs='+', required=True)
    x.add_argument('--update', action='append', default=[], metavar='ROW=JOB')
    x.set_defaults(func=cmd_import)

    p = sub.add_parser('migrate', parents=[common], help='copy data into a new version-2 directory')
    p.add_argument('--output', required=True)
    p.set_defaults(func=cmd_migrate)
    p = sub.add_parser('project-evidence', help='pinned local Git evidence and user attestations')
    es = p.add_subparsers(dest='action', required=True)
    x = es.add_parser('propose', parents=[common])
    x.add_argument('--file', required=True)
    for action in ('confirm', 'retire'):
        x = es.add_parser(action, parents=[common])
        x.add_argument('id')
    x = es.add_parser('check', parents=[common])
    x.add_argument('id', nargs='?')
    es.add_parser('list', parents=[common])
    p.set_defaults(func=cmd_project_evidence)

    p = sub.add_parser('letter', help='review optional cover letters')
    ls = p.add_subparsers(dest='action', required=True)
    for action in ('propose', 'show', 'accept', 'remove', 'render'):
        x = ls.add_parser(action, parents=[common])
        x.add_argument('job')
        if action == 'propose':
            x.add_argument('--file', required=True)
        if action in ('show', 'remove'):
            x.add_argument('--proposal', action='store_true')
        if action == 'render':
            x.add_argument('--output', required=True)
            x.add_argument('--pdf', action='store_true')
    p.set_defaults(func=cmd_letter)

    p = sub.add_parser('stories', help='evidence-backed interview preparation')
    ss = p.add_subparsers(dest='action', required=True)
    x = ss.add_parser('propose', parents=[common])
    x.add_argument('--file', required=True)
    x.add_argument('--id', help='replace the pending draft for an existing story')
    x = ss.add_parser('accept', parents=[common])
    x.add_argument('id')
    x = ss.add_parser('show', parents=[common])
    x.add_argument('id')
    x.add_argument('--proposal', action='store_true')
    x = ss.add_parser('check', parents=[common])
    x.add_argument('id', nargs='?')
    ss.add_parser('list', parents=[common])
    x = ss.add_parser('export', parents=[common])
    x.add_argument('id')
    x.add_argument('--output', required=True)
    x = ss.add_parser('suggest', parents=[common])
    x.add_argument('job')
    p.set_defaults(func=cmd_stories)

    p = sub.add_parser("pipeline", parents=[common], help="review states, listing freshness, blockers and next actions")
    p.add_argument("--output", help="export HTML and JSON into a new directory")
    p.set_defaults(func=cmd_pipeline)

    p = sub.add_parser("insights", parents=[common], help="recorded outcomes and recurring current-profile gaps")
    p.add_argument("--historical", action="store_true")
    p.add_argument("--from", dest="start", help="inclusive submission date")
    p.add_argument("--to", dest="end", help="inclusive submission date")
    p.set_defaults(func=cmd_insights)

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
    p.add_argument("--style", help="validated presentation JSON; saved for later renders of this job ({} resets)")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("followup", help="manual local follow-up dates")
    fs = p.add_subparsers(dest="action", required=True)
    x = fs.add_parser("set", parents=[common])
    x.add_argument("job")
    x.add_argument("--date", required=True)
    x.add_argument("--note", default="")
    x.add_argument("--id", help="reschedule/reactivate an unfinished follow-up")
    x = fs.add_parser("list", parents=[common])
    x.add_argument("job")
    for action in ("complete", "cancel"):
        x = fs.add_parser(action, parents=[common])
        x.add_argument("job")
        x.add_argument("id")
    p.set_defaults(func=cmd_followup)

    p = sub.add_parser("track", help="set tracking status (applied freezes a snapshot)")
    p.add_argument("job")
    p.add_argument("status", choices=jobs_mod.STATUSES)
    p.add_argument("--note")
    p.set_defaults(func=cmd_track)

    p = sub.add_parser("note", help="add a tracking note")
    p.add_argument("job")
    p.add_argument("text")
    p.set_defaults(func=cmd_note)
    p = sub.add_parser("batch-export", parents=[common], help="export selected resumes into a new review pack")
    p.add_argument("jobs", nargs="+")
    p.add_argument("--output", required=True)
    p.add_argument("--pdf", action="store_true")
    p.add_argument("--accepted", action="store_true", help="export accepted resumes; default is pending proposals")
    p.add_argument("--style", help="presentation JSON for this export only")
    p.set_defaults(func=cmd_batch)
    p = sub.add_parser("ats", parents=[common], help="local ATS preflight: keyword gaps, content and optional PDF text checks")
    p.add_argument("job")
    p.add_argument("--proposal", action="store_true", help="check the pending draft instead of the accepted resume")
    p.add_argument("--pdf", metavar="FILE", help="also check text extracted from this exported PDF")
    p.set_defaults(func=cmd_ats)
    return parser


def cmd_stories(args):
    from . import stories
    if args.action == 'propose':
        result = stories.propose(store.load_input(args.file), args.id)
    elif args.action == 'accept':
        result = stories.accept(args.id)
    elif args.action == 'show':
        result = stories.show(args.id, args.proposal)
    elif args.action in ('list', 'check'):
        result = stories.check(getattr(args, 'id', None))
    elif args.action == 'export':
        result = stories.export(args.id, args.output)
    else:
        result = stories.suggest(args.job)
    out(result, True)
    if args.action == 'check':
        return 1 if any(item['errors'] for item in result) else 0


def cmd_letter(args):
    from . import letters, ledger
    ledger.require_v2()
    if args.action == 'propose':
        result = letters.propose(args.job, store.load_input(args.file))
    elif args.action == 'accept':
        result = letters.accept(args.job)
    elif args.action == 'remove':
        letters.remove(args.job, args.proposal)
        result = {'removed': 'proposal' if args.proposal else 'accepted'}
    elif args.action == 'render':
        result = letters.export(args.job, args.output, args.pdf)
    else:
        result = package_mod.load(args.job).get('letter_proposal' if args.proposal else 'letter')
    out(result, True)


def cmd_migrate(args):
    from . import migration
    result = migration.migrate(args.output)
    out(result, True)


def cmd_project_evidence(args):
    from . import ledger
    if args.action == 'propose':
        result = ledger.propose(store.load_input(args.file))
    elif args.action in ('confirm', 'retire'):
        result = ledger.action(args.id, args.action)
    elif args.action == 'check':
        result = ledger.check(args.id)
    else:
        result = ledger.load()['records']
    out(result, True)
    if args.action == 'check':
        return 1 if any(r['state'] != 'verified' for r in result) else 0


def cmd_import(args):
    from . import imports
    data = store.load_input(args.file)
    if args.action == 'import-preview':
        result = imports.preview(data)
    else:
        updates = {}
        for value in args.update:
            try:
                number, jid = value.split('=', 1)
                number = int(number)
            except ValueError:
                raise ResuError('--update must be ROW=JOB.') from None
            if number in updates:
                raise ResuError('Duplicate update row.')
            updates[number] = jid
        result = imports.apply(data, store.load_input(args.preview), args.select, updates)
    # Preview is always JSON so it can be saved and passed unchanged to apply.
    out(result, True)


def cmd_followup(args):
    from . import followups
    if args.action == 'set':
        result = followups.set_followup(args.job, args.date, args.note, args.id)
    elif args.action == 'list':
        result = followups.rows(jobs_mod.load(args.job))
    else:
        result = followups.finish(args.job, args.id, 'completed' if args.action == 'complete' else 'cancelled')
    out(result, args.json, json.dumps(result, indent=2, ensure_ascii=False))


def cmd_pipeline(args):
    from . import pipeline
    result = pipeline.report()
    if args.output:
        result["files"] = pipeline.export(result, args.output)
    text = pipeline.text_report(result)
    if args.output:
        text += "\nHTML report: " + result["files"]["html"]
    out(result, args.json, text)
    return 1 if result["errors"] else 0


def cmd_insights(args):
    from . import insights, history
    if (args.start or args.end) and not args.historical:
        raise ResuError("Date filters require --historical.")
    result = history.report(args.start, args.end) if args.historical else insights.report()
    out(result, args.json, history.text_report(result) if args.historical else insights.text_report(result))
    return 1 if result["errors"] else 0


def cmd_ats(args):
    from . import ats
    result = ats.check(args.job, args.proposal, args.pdf)
    out(result, args.json, ats.text_report(result))
    return 1 if any(i['severity'] == 'error' for i in result['issues']) else 0


def cmd_batch(args):
    from . import batch
    result = batch.export(args.jobs, args.output, args.pdf, args.accepted,
                          store.load_input(args.style) if args.style else None)
    out(result, args.json, f"Exported {len(result['jobs'])} resumes to {result['output']}\n"
        + ("PDF errors: " + "; ".join(result['errors']) if result['errors'] else "Review index.html before use."))
    return 1 if result['errors'] else 0


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
        from contextlib import nullcontext
        isolated = args.command in ('demo', 'doctor') or (args.command == 'profile' and args.action == 'template')
        with nullcontext() if isolated else store.command_lock():
            result = args.func(args)
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130
    except ResuError as exc:
        print(f"error: {exc}", file=sys.stderr)
        for detail in exc.details:
            print(f"  - {detail}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError) as exc:
        print(f"error: could not read or write the requested file: {exc}", file=sys.stderr)
        return 1
    return result if isinstance(result, int) else 0
