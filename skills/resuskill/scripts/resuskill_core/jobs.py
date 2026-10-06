"""Saved jobs: creation, listing and requirement validation.

The job description is untrusted data. It is stored and quoted, never executed or obeyed.
"""

from __future__ import annotations

from . import store
from .util import ResuError, date_key, is_valid_date, norm_text, now_iso, slugify

CATEGORIES = {"skill", "education", "experience", "location", "authorization", "availability", "other"}
IMPORTANCE = {"required", "preferred", "unspecified"}
DEGREE_LEVELS = ["associate", "bachelor", "master", "phd"]
CRITERION_TYPES = {
    "skill", "degree", "graduation_window", "location", "authorization", "availability", "years_experience",
}
STATUSES = ["saved", "applied", "assessment", "interview", "rejected", "offer", "withdrawn"]


def load(job_id: str) -> dict:
    job = store.read_json(store.job_dir(job_id) / "job.json")
    if job is None:
        raise ResuError(f"Job {job_id!r} is missing job.json")
    return job


def save(job: dict) -> None:
    job["updated_at"] = now_iso()
    store.write_json(store.job_dir(job["id"]) / "job.json", job)


def list_jobs() -> list[dict]:
    jobs = []
    for path in sorted(store.jobs_dir().iterdir()):
        data = store.read_json(path / "job.json") if path.is_dir() else None
        if data:
            jobs.append(data)
    return sorted(jobs, key=lambda j: j.get("created_at", ""), reverse=True)


def add(company: str, title: str, description: str, location: str = "", url: str = "") -> dict:
    company, title, description = company.strip(), title.strip(), description.strip()
    missing = [n for n, v in (("company", company), ("title", title), ("description", description)) if not v]
    if missing:
        raise ResuError(f"Missing required job field(s): {', '.join(missing)}")
    base = f"{slugify(company, 24)}-{slugify(title, 32)}"
    job_id, n = base, 1
    while (store.jobs_dir() / job_id).exists():
        n += 1
        job_id = f"{base}-{n}"
    (store.jobs_dir() / job_id).mkdir()
    created = now_iso()
    job = {
        "id": job_id,
        "company": company,
        "title": title,
        "location": location.strip(),
        "url": url.strip(),
        "description": description,
        "revision": 1,
        "created_at": created,
        "requirements": [],
        "evidence": {},
        "overrides": {},
        "questions": [],
        "tracking": {"status": "saved", "history": [{"status": "saved", "at": created}], "notes": []},
    }
    save(job)
    return job


# ---------------------------------------------------------------- requirements

def _validate_criterion(crit, where: str, errors: list[str]):
    if crit in (None, {}):
        return None
    if not isinstance(crit, dict):
        errors.append(f"{where}.criterion must be an object or null")
        return None
    kind = crit.get("type")
    if kind not in CRITERION_TYPES:
        errors.append(f"{where}.criterion.type must be one of {sorted(CRITERION_TYPES)}")
        return None
    clean = {"type": kind}
    if kind == "skill":
        skills = [s.strip() for s in crit.get("skills") or [] if isinstance(s, str) and s.strip()]
        if not skills:
            errors.append(f"{where}.criterion.skills must list at least one skill")
        match = crit.get("match", "all")
        if match not in ("all", "any"):
            errors.append(f"{where}.criterion.match must be 'all' or 'any'")
        clean.update(skills=skills, match=match)
    elif kind == "degree":
        level = str(crit.get("level", "")).lower()
        if level not in DEGREE_LEVELS:
            errors.append(f"{where}.criterion.level must be one of {DEGREE_LEVELS}")
        status = crit.get("status", "any")
        if status not in ("any", "completed", "pursuing"):
            errors.append(f"{where}.criterion.status must be any, completed or pursuing")
        clean.update(level=level, fields=[f.strip() for f in crit.get("fields") or [] if isinstance(f, str) and f.strip()], status=status)
    elif kind == "graduation_window":
        start, end = crit.get("from"), crit.get("to")
        if not start and not end:
            errors.append(f"{where}.criterion needs 'from' and/or 'to'")
        for name, value in (("from", start), ("to", end)):
            if value and not is_valid_date(value):
                errors.append(f"{where}.criterion.{name} must be a date")
        clean.update({"from": start or None, "to": end or None})
    elif kind == "location":
        mode = crit.get("work_mode")
        if mode not in (None, "remote", "hybrid", "onsite"):
            errors.append(f"{where}.criterion.work_mode must be remote, hybrid, onsite or null")
        locations = [l.strip() for l in crit.get("locations") or [] if isinstance(l, str) and l.strip()]
        if not locations and not mode:
            errors.append(f"{where}.criterion needs locations and/or work_mode")
        clean.update(locations=locations, work_mode=mode)
    elif kind == "authorization":
        country = str(crit.get("country", "")).strip().upper()
        if not country:
            errors.append(f"{where}.criterion.country is required")
        sponsorship = crit.get("sponsorship_available")
        if sponsorship not in (True, False, None):
            errors.append(f"{where}.criterion.sponsorship_available must be true, false or null")
        clean.update(country=country, sponsorship_available=sponsorship)
    elif kind == "availability":
        start_by, start_from = crit.get("start_by"), crit.get("start_from")
        if not start_by and not start_from:
            errors.append(f"{where}.criterion needs start_by and/or start_from")
        for name, value in (("start_by", start_by), ("start_from", start_from)):
            if value and not is_valid_date(value):
                errors.append(f"{where}.criterion.{name} must be a date")
        clean.update(start_by=start_by or None, start_from=start_from or None)
    elif kind == "years_experience":
        years = crit.get("years")
        if not isinstance(years, (int, float)) or years < 0:
            errors.append(f"{where}.criterion.years must be a non-negative number")
        clean.update(years=years, area=str(crit.get("area", "")).strip())
    return clean


def validate_requirements(job: dict, items) -> list[dict]:
    if isinstance(items, dict) and "requirements" in items:
        items = items["requirements"]
    if not isinstance(items, list):
        raise ResuError("Requirements must be a JSON list (or an object with a 'requirements' list)")
    description = norm_text(job["description"])
    errors: list[str] = []
    clean: list[dict] = []
    used_ids: set[str] = set()
    for index, item in enumerate(items):
        where = f"requirements[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue
        text = str(item.get("text", "")).strip()
        excerpt = str(item.get("excerpt", "")).strip()
        category = item.get("category", "other")
        importance = item.get("importance", "unspecified")
        if not text:
            errors.append(f"{where}.text is required")
        if category not in CATEGORIES:
            errors.append(f"{where}.category must be one of {sorted(CATEGORIES)}")
        if importance not in IMPORTANCE:
            errors.append(f"{where}.importance must be one of {sorted(IMPORTANCE)}")
        if not excerpt:
            errors.append(f"{where}.excerpt is required (a verbatim quote from the description)")
        elif norm_text(excerpt) not in description:
            errors.append(f"{where}.excerpt not found in the job description: {excerpt[:80]!r}")
        req_id = str(item.get("id") or "").strip() or f"r{index + 1}"
        if req_id in used_ids:
            errors.append(f"{where}.id {req_id!r} is duplicated")
        used_ids.add(req_id)
        crit = _validate_criterion(item.get("criterion"), where, errors)
        clean.append({"id": req_id, "text": text, "category": category, "importance": importance, "excerpt": excerpt, "criterion": crit})
    if errors:
        raise ResuError("Requirements rejected; nothing was saved. Correct them and retry.", errors)
    return clean


def set_requirements(job_id: str, items) -> dict:
    job = load(job_id)
    reqs = validate_requirements(job, items)
    ids = {r["id"] for r in reqs}
    job["requirements"] = reqs
    job["evidence"] = {k: v for k, v in job.get("evidence", {}).items() if k in ids}
    job["overrides"] = {k: v for k, v in job.get("overrides", {}).items() if k in ids}
    job["revision"] += 1
    save(job)
    return job


def requirement(job: dict, req_id: str) -> dict:
    for req in job["requirements"]:
        if req["id"] == req_id:
            return req
    raise ResuError(f"Job {job['id']} has no requirement {req_id!r}")


def degree_level(degree: str) -> int | None:
    """Index into DEGREE_LEVELS for a free-text degree, or None when unrecognised."""
    text = norm_text(degree).replace(".", "").replace("'", "")
    patterns = [
        (3, ("phd", "doctor", "dphil", "doctorate")),
        (2, ("master", "ms ", "msc", "meng", "mtech", "mba", "ma ", "mca", "mphil")),
        (1, ("bachelor", "bs ", "bsc", "ba ", "beng", "btech", "be ", "bca", "bba", "ab ")),
        (0, ("associate", "aa ", "as ")),
    ]
    padded = f"{text} "
    for level, needles in patterns:
        if any(padded.startswith(n) or f" {n}" in f" {padded}" for n in needles):
            return level
    return None


def is_future(date_value) -> bool:
    key = date_key(date_value, end_of_period=True)
    from .util import today_key

    return bool(key) and key > today_key()
