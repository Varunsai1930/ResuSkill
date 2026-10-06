"""Application tracking and frozen submitted snapshots."""

from __future__ import annotations

import shutil

from . import checklist as checklist_mod
from . import jobs as jobs_mod
from . import package as package_mod
from . import profile as profile_mod
from . import render, store
from .util import ResuError, now_iso, stamp


def set_status(job_id: str, status: str, note: str = "") -> dict:
    status = status.lower()
    if status not in jobs_mod.STATUSES:
        raise ResuError(f"Status must be one of {', '.join(jobs_mod.STATUSES)}")
    job = jobs_mod.load(job_id)
    tracking = job["tracking"]
    if status == "applied":
        if tracking.get("snapshot"):
            raise ResuError(f"Already recorded as applied with snapshot {tracking['snapshot']}")
        tracking["snapshot"] = snapshot(job_id)
        tracking["applied_at"] = now_iso()
    tracking["status"] = status
    tracking.setdefault("history", []).append({"status": status, "at": now_iso(), "note": note.strip()})
    if note.strip():
        tracking.setdefault("notes", []).append({"text": note.strip(), "at": now_iso()})
    jobs_mod.save(job)
    return job


def snapshot(job_id: str) -> str:
    """Freeze the approved package, its rendered files and the inputs it was built from."""
    job = jobs_mod.load(job_id)
    prof = profile_mod.load()
    pkg = package_mod.load(job_id)
    state = package_mod.review_state(job, pkg, prof)
    if state != package_mod.APPROVED:
        raise ResuError(
            f"Package is {state.upper()}. Record Applied only for a current approved package: "
            "run `package check`, fix blockers, then `package approve`."
        )
    outputs = render.render(job_id)
    name = stamp()
    folder = store.job_dir(job_id) / "snapshots" / name
    folder.mkdir(parents=True)
    store.write_json(folder / "package.json", {
        "job": {k: job[k] for k in ("id", "company", "title", "location", "url", "revision")},
        "approval": pkg["approval"],
        "package": package_mod.resolved(job, prof, pkg),
        "checklist": checklist_mod.evaluate(job, prof),
        "profile": prof,
        "frozen_at": now_iso(),
    })
    shutil.copy2(outputs["resume"], folder / "resume.html")
    shutil.copy2(outputs["review"], folder / "review.html")
    pdf = render.out_dir(job_id) / render.pdf_name(prof)
    if pdf.exists():
        shutil.copy2(pdf, folder / pdf.name)
    return name


def add_note(job_id: str, text: str) -> dict:
    if not text.strip():
        raise ResuError("Note text is empty")
    job = jobs_mod.load(job_id)
    job["tracking"].setdefault("notes", []).append({"text": text.strip(), "at": now_iso()})
    jobs_mod.save(job)
    return job


def rows() -> list[dict]:
    prof = profile_mod.load(required=False)
    table = []
    for job in jobs_mod.list_jobs():
        pkg = package_mod.load(job["id"])
        counts = checklist_mod.summary(checklist_mod.evaluate(job, prof)) if prof and job.get("requirements") else None
        table.append({
            "id": job["id"],
            "company": job["company"],
            "title": job["title"],
            "review": package_mod.review_state(job, pkg, prof),
            "status": job["tracking"]["status"],
            "updated": (job["tracking"]["history"][-1]["at"] if job["tracking"].get("history") else job["created_at"])[:10],
            "checklist": counts,
        })
    return table
