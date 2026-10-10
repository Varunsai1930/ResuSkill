"""A fictional application, isolated from the user's real data."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from . import jobs, package, profile, render
from .util import ResuError


def create(output: str | None = None) -> dict:
    if output:
        folder = Path(output).expanduser().resolve()
        try:
            folder.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise ResuError("Demo output already exists. Choose a new directory; existing data was not changed.") from exc
    else:
        folder = Path(tempfile.mkdtemp(prefix="resuskill-demo-")).resolve()
    previous = os.environ.get("RESUSKILL_HOME")
    os.environ["RESUSKILL_HOME"] = str(folder)
    try:
        profile.save({
            "contact": {"name": "Alex Example", "email": "alex@example.com"},
            "summary": "Developer who builds Python tools.",
            "projects": [{"name": "Task Helper", "technologies": ["Python"],
                          "bullets": ["Built a Python tool that exports task lists to CSV"]}],
            "skills": ["Python"], "skills_absent": ["Rust"],
        })
        job = jobs.add("Fictional Demo Co", "Python Developer", "Python required. Rust preferred.")
        job_id = job["id"]
        jobs.set_requirements(job_id, [
            {"text": "Python", "excerpt": "Python required.", "importance": "required",
             "criterion": {"type": "skill", "skills": ["Python"]}},
            {"text": "Rust", "excerpt": "Rust preferred.", "importance": "preferred",
             "criterion": {"type": "skill", "skills": ["Rust"]}},
        ])
        package.propose_resume(job_id, {"projects": [{"entry": "proj-1", "bullets": [
            {"text": "Built a Python tool that exports task lists to CSV", "sources": ["proj-1-b1"]}]}]})
        package.accept_resume(job_id)
        package.add_question(job_id, "Why are you interested in this role?", True, 100, "words", None)
        package.propose_answers(job_id, [{"question_id": "q1", "text": "I build Python tools and would like to apply that experience here.",
                                          "sources": ["summary"]}])
        package.accept_answers(job_id, [])
        package.add_question(job_id, "What is your desired salary?", False, None, "chars", None)
        outputs = render.render(job_id)
        blockers, warnings = package.check(job_id)
        return {"data_dir": str(folder), "job_id": job_id, **outputs, "blockers": blockers,
                "warnings": warnings, "next": "Fictional draft only. Review the HTML. Set RESUSKILL_HOME to data_dir for demo commands. The optional salary question needs a user answer or explicit skip before approval."}
    finally:
        if previous is None:
            os.environ.pop("RESUSKILL_HOME", None)
        else:
            os.environ["RESUSKILL_HOME"] = previous
