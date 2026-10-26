"""Saved jobs: creation, listing and requirement validation.

The job description is untrusted data. It is stored and quoted, never executed or obeyed.
"""

from __future__ import annotations

import re

from . import SCHEMA_VERSION, store, input_schema
from . import listing
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
    _check_stored(job, job_id)
    return job


# Fields every command relies on; all have been written since the first job format.
_STORED_FIELDS = {"id": str, "company": str, "title": str, "description": str,
                  "revision": int, "requirements": list, "tracking": dict}
_STORED_CRITERION_FIELDS = {
    "skill": {"skills": list, "match": str},
    "degree": {"level": str, "fields": list, "status": str},
    "authorization": {"country": str},
}


def _check_stored(job, folder: str) -> None:
    """Refuse a damaged job.json before any command reads its fields."""
    store.check_version(job, "job")
    bad = [k for k, kind in _STORED_FIELDS.items() if type(job.get(k)) is not kind]
    if not bad and not isinstance(job["tracking"].get("status"), str):
        bad = ["tracking.status"]
    if bad:
        raise ResuError(f"Stored job has missing or invalid {', '.join(bad)}; restore a valid backup")
    if job["id"] != folder:
        raise ResuError(f"Stored job id {job['id']!r} does not match its folder {folder!r}; "
                        "a copied folder must keep its original name or be removed")
    from . import followups
    followups.validate(job["tracking"].get("followups", []))
    _check_auxiliary(job)
    if 'listing' in job:
        listing.normalize(job['listing'])
    try:
        input_schema.check(job["requirements"], input_schema.REQUIREMENTS, "stored requirements")
    except ResuError as exc:
        raise ResuError("Stored job has invalid requirements; restore a valid backup", exc.details) from exc
    errors = []
    for index, requirement in enumerate(job["requirements"]):
        where = f"requirements[{index}]"
        for field in ("id", "text", "excerpt", "category", "importance"):
            if type(requirement.get(field)) is not str:
                errors.append(f"{where}.{field} must be text")
        criterion = requirement.get("criterion")
        if criterion:
            fields = {"type": str} | _STORED_CRITERION_FIELDS.get(criterion.get("type"), {})
            for field, kind in fields.items():
                if type(criterion.get(field)) is not kind:
                    errors.append(f"{where}.criterion.{field} is missing or invalid")
            _validate_criterion(criterion, where, errors)
    if errors:
        raise ResuError("Stored job has invalid requirements; restore a valid backup", errors)


def _check_auxiliary(job: dict) -> None:
    """Check review metadata before checklist/answer code dereferences it."""
    from . import questions as q_mod

    specs = {
        'evidence': {'*': {'sources': [str], 'profile_revision': int,
                           'confirmed_at': str, 'source_hashes': input_schema.nullable({'*': str})}},
        'overrides': {'*': {'status': str, 'reason': str, 'at': str, 'profile_revision': int}},
        'questions': [{'id': str, 'text': str, 'required': bool, 'limit': input_schema.nullable(int),
                       'limit_unit': str, 'category': str, 'factual_key': input_schema.nullable(str), 'added_at': str}],
    }
    try:
        input_schema.check({key: job[key] for key in specs if key in job}, specs, 'stored job review metadata')
    except ResuError as exc:
        raise ResuError('Stored job review metadata is damaged; restore a valid backup. Nothing was changed.', exc.details) from exc
    problems = []
    for key, override in (job.get('overrides') or {}).items():
        if (override.get('status') not in ('met', 'unmet', 'unknown')
                or not override.get('reason') or type(override.get('profile_revision')) is not int):
            problems.append('overrides.' + key)
    seen = set()
    for question in job.get('questions') or []:
        qid = question.get('id', '')
        if (not re.fullmatch(r'q[1-9]\d*', qid) or qid in seen or not question.get('text')
                or type(question.get('required')) is not bool
                or question.get('category') not in q_mod.CATEGORIES
                or question.get('limit_unit') not in ('chars', 'words')
                or (question.get('limit') is not None and question['limit'] <= 0)):
            problems.append('questions.' + qid)
        seen.add(qid)
    if problems:
        raise ResuError('Stored job review metadata is incomplete; restore a valid backup. Nothing was changed.', problems)


def save(job: dict) -> None:
    job["schema_version"] = store.data_version()
    job["updated_at"] = now_iso()
    store.write_json(store.job_dir(job["id"]) / "job.json", job)


def list_jobs(problems: list[tuple[str, str]] | None = None) -> list[dict]:
    """Readable jobs, newest first. An unreadable job is reported in ``problems`` and skipped,
    so one damaged file never hides the others."""
    jobs = []
    for path in sorted(store.jobs_dir().iterdir()):
        if not path.is_dir():
            continue
        try:
            data = store.read_json(path / "job.json")
            if data is None:
                raise ResuError('Job folder has no valid job.json (missing or null); restore a valid backup.')
            _check_stored(data, path.name)
        except ResuError as exc:
            if problems is not None:
                problems.append((path.name, str(exc)))
            continue
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

def observe(job_id: str, data) -> dict:
    """Replace the complete reviewed observation, invalidating older approval."""
    clean = listing.normalize(data)
    job = load(job_id)
    if job.get('listing') != clean:
        job['listing'] = clean
        job['revision'] += 1
        save(job)
    return job

def _str_list(crit: dict, field: str, where: str, errors: list[str]) -> list[str]:
    """A list of non-empty strings; a bare string is an error, not a list of characters."""
    value = crit.get(field)
    if value in (None, []):
        return []
    if not isinstance(value, list):
        errors.append(f"{where}.criterion.{field} must be a list")
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


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
        skills = _str_list(crit, "skills", where, errors)
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
        clean.update(level=level, fields=_str_list(crit, "fields", where, errors), status=status)
    elif kind in ("graduation_window", "availability"):
        start_field, end_field = ("from", "to") if kind == "graduation_window" else ("start_from", "start_by")
        start, end = crit.get(start_field), crit.get(end_field)
        if not start and not end:
            errors.append(f"{where}.criterion needs {start_field} and/or {end_field}")
        for name, value in ((start_field, start), (end_field, end)):
            if value and not is_valid_date(value):
                errors.append(f"{where}.criterion.{name} must be a date")
        if start and end and is_valid_date(start) and is_valid_date(end):
            if date_key(start) > date_key(end, end_of_period=True):
                errors.append(f"{where}.criterion.{start_field} must not be after {end_field}")
        clean.update({start_field: start or None, end_field: end or None})
    elif kind == "location":
        mode = crit.get("work_mode")
        if mode not in (None, "remote", "hybrid", "onsite"):
            errors.append(f"{where}.criterion.work_mode must be remote, hybrid, onsite or null")
        locations = _str_list(crit, "locations", where, errors)
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
    elif kind == "years_experience":
        years = crit.get("years")
        if not isinstance(years, (int, float)) or years < 0:
            errors.append(f"{where}.criterion.years must be a non-negative number")
        clean.update(years=years, area=str(crit.get("area", "")).strip())
    return clean


def validate_requirements(job: dict, items) -> list[dict]:
    if isinstance(items, dict) and "requirements" in items:
        input_schema.check(items, {"requirements": input_schema.REQUIREMENTS}, "requirement input")
        items = items["requirements"]
    if not isinstance(items, list):
        raise ResuError("Requirements must be a JSON list (or an object with a 'requirements' list)")
    input_schema.check(items, input_schema.REQUIREMENTS, "requirements")
    description = norm_text(job["description"])
    errors: list[str] = []
    clean: list[dict] = []
    used_ids: set[str] = set()
    # Requirements without an id keep the id of the saved requirement with the same text and
    # excerpt; new ones get a number never used before, so evidence and overrides stay attached.
    previous = {}
    for requirement in job.get("requirements") or []:
        previous.setdefault(_requirement_key(requirement), []).append(requirement["id"])
    explicit = {str(i.get("id") or "").strip() for i in items if isinstance(i, dict)} - {""}
    previous_ids = {rid for ids in previous.values() for rid in ids}
    counter = max([int(job.get("requirement_counter", 0))] + [
        int(m.group(1)) for rid in explicit | previous_ids for m in [re.fullmatch(r"r(\d+)", rid)] if m
    ])
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
        req_id = str(item.get("id") or "").strip()
        if not req_id:
            reuse = next((rid for rid in previous.get(_requirement_key({"text": text, "excerpt": excerpt}), [])
                          if rid not in used_ids and rid not in explicit), None)
            if reuse:
                req_id = reuse
            else:
                counter += 1
                req_id = f"r{counter}"
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
    old = {r["id"]: r for r in job.get("requirements") or []}
    # Evidence and overrides were confirmed for a specific requirement; drop them when it changed.
    unchanged = {r["id"] for r in reqs if old.get(r["id"]) == r}
    job["requirements"] = reqs
    job["requirements_reviewed_at"] = now_iso()
    job["evidence"] = {k: v for k, v in job.get("evidence", {}).items() if k in unchanged}
    job["overrides"] = {k: v for k, v in job.get("overrides", {}).items() if k in unchanged}
    numbers = [int(r["id"][1:]) for r in reqs if re.fullmatch(r"r\d+", r["id"])]
    job["requirement_counter"] = max([int(job.get("requirement_counter", 0))] + numbers)
    job["revision"] += 1
    save(job)
    return job


def _requirement_key(req: dict) -> str:
    return f"{norm_text(req.get('text', ''))}|{norm_text(req.get('excerpt', ''))}"


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
