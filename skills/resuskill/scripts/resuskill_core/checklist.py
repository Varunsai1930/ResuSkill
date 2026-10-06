"""Deterministic requirement checklist: Met, Unmet or Unknown, always with its basis.

- Met: confirmed profile evidence satisfies the requirement.
- Unmet: confirmed profile evidence conflicts with it.
- Unknown: information is missing, ambiguous or cannot be compared reliably.
"""

from __future__ import annotations

from . import jobs as jobs_mod
from . import profile as profile_mod
from .skills import canon
from .util import ResuError, date_key, norm_text, now_iso

MET, UNMET, UNKNOWN = "met", "unmet", "unknown"
STATUSES = (MET, UNMET, UNKNOWN)


def _skill(crit: dict, prof: dict) -> tuple[str, str]:
    have = profile_mod.skill_keys(prof)
    absent = {canon(s) for s in prof.get("skills_absent") or []}
    present = [s for s in crit["skills"] if canon(s) in have]
    lacking = [s for s in crit["skills"] if canon(s) in absent and canon(s) not in have]
    missing = [s for s in crit["skills"] if s not in present and s not in lacking]
    if crit["match"] == "any":
        if present:
            return MET, f"Profile lists {', '.join(present)}"
        if len(lacking) == len(crit["skills"]):
            return UNMET, f"User confirmed they lack {', '.join(lacking)}"
        return UNKNOWN, f"Not in profile: {', '.join(missing)}"
    if len(present) == len(crit["skills"]):
        return MET, f"Profile lists {', '.join(present)}"
    if lacking:
        return UNMET, f"User confirmed they lack {', '.join(lacking)}"
    return UNKNOWN, f"Not in profile: {', '.join(missing)}"


def _field_matches(field: str, wanted: list[str]) -> bool:
    if not wanted:
        return True
    field_n = norm_text(field)
    return bool(field_n) and any(norm_text(w) in field_n or field_n in norm_text(w) for w in wanted)


def _degree(crit: dict, prof: dict) -> tuple[str, str]:
    education = prof.get("education") or []
    if not education:
        return UNKNOWN, "No education in profile"
    needed = jobs_mod.DEGREE_LEVELS.index(crit["level"])
    levels = []
    for entry in education:
        level = jobs_mod.degree_level(entry.get("degree", ""))
        levels.append(level)
        if level is None or level < needed:
            continue
        end = entry.get("graduation") or entry.get("end")
        pursuing = end == "present" or jobs_mod.is_future(end)
        if crit["status"] == "pursuing" and not pursuing:
            continue
        if crit["status"] == "completed" and (pursuing or not end):
            continue
        if not _field_matches(entry.get("field", ""), crit["fields"]):
            continue
        label = f"{entry.get('degree', '')} {entry.get('field', '')}".strip()
        return MET, f"{label} at {entry.get('institution', '')} ({entry['id']})"
    if None not in levels and max(levels) < needed:
        return UNMET, f"Highest degree in profile is below {crit['level']}"
    return UNKNOWN, "Degree level, field or status cannot be confirmed from the profile"


def _graduation(crit: dict, prof: dict) -> tuple[str, str]:
    grad = profile_mod.graduation_date(prof)
    if not grad:
        return UNKNOWN, "No graduation date in profile"
    grad_key = date_key(grad)
    if crit.get("from") and grad_key < date_key(crit["from"]):
        return UNMET, f"Graduation {grad} is before {crit['from']}"
    if crit.get("to") and grad_key > date_key(crit["to"], end_of_period=True):
        return UNMET, f"Graduation {grad} is after {crit['to']}"
    return MET, f"Graduation {grad} is inside the window"


def _location(crit: dict, prof: dict) -> tuple[str, str]:
    prefs = prof.get("preferences") or {}
    mode = prefs.get("work_mode")
    results: list[tuple[str, str]] = []
    if crit.get("work_mode"):
        wanted = crit["work_mode"]
        if not mode:
            results.append((UNKNOWN, "No work-mode preference in profile"))
        elif mode == "any" or mode == wanted:
            results.append((MET, f"Profile work mode '{mode}' fits '{wanted}'"))
        elif mode == "remote" and wanted in ("onsite", "hybrid"):
            results.append((UNMET, f"Profile wants remote only; job is {wanted}"))
        else:
            results.append((UNKNOWN, f"Profile prefers '{mode}'; job is '{wanted}'"))
    if crit.get("locations"):
        places = [norm_text(p) for p in prefs.get("locations") or []]
        if prof.get("contact", {}).get("location"):
            places.append(norm_text(prof["contact"]["location"]))
        hits = [loc for loc in crit["locations"] if any(norm_text(loc) in p or p in norm_text(loc) for p in places if p)]
        if hits:
            results.append((MET, f"Profile location/preferences include {', '.join(hits)}"))
        else:
            results.append((UNKNOWN, "Location not in profile preferences (relocation unknown)"))
    if any(s == UNMET for s, _ in results):
        return next(r for r in results if r[0] == UNMET)
    if results and all(s == MET for s, _ in results):
        return MET, "; ".join(b for _, b in results)
    return UNKNOWN, "; ".join(b for s, b in results if s != MET) or "Not comparable"


def _authorization(crit: dict, prof: dict) -> tuple[str, str]:
    record = next((a for a in prof.get("authorization") or [] if a["country"] == crit["country"]), None)
    if not record or record.get("authorized") is None:
        return UNKNOWN, f"Work authorization for {crit['country']} is not recorded"
    sponsor = crit.get("sponsorship_available")
    needs = record.get("requires_sponsorship")
    if record["authorized"]:
        if needs and sponsor is False:
            return UNMET, "Profile requires sponsorship; job offers none"
        if needs and sponsor is None:
            return UNKNOWN, "Profile requires sponsorship; job does not say if it sponsors"
        if needs is None:
            return UNKNOWN, "Sponsorship need is not recorded"
        return MET, f"Authorized to work in {crit['country']}"
    if sponsor is True:
        return MET, "Not yet authorized, but the job offers sponsorship"
    if sponsor is False:
        return UNMET, f"Not authorized in {crit['country']} and the job offers no sponsorship"
    return UNKNOWN, "Not authorized; job does not say if it sponsors"


def _availability(crit: dict, prof: dict) -> tuple[str, str]:
    start = (prof.get("availability") or {}).get("start_date")
    if not start:
        return UNKNOWN, "No start date in profile"
    if crit.get("start_by") and date_key(start) > date_key(crit["start_by"], end_of_period=True):
        return UNMET, f"Available from {start}, after {crit['start_by']}"
    return MET, f"Available from {start}"


CHECKS = {
    "skill": _skill,
    "degree": _degree,
    "graduation_window": _graduation,
    "location": _location,
    "authorization": _authorization,
    "availability": _availability,
}


def evaluate(job: dict, prof: dict) -> list[dict]:
    sources = profile_mod.sources(prof)
    results = []
    for req in job["requirements"]:
        evidence_ids = [i for i in (job.get("evidence", {}).get(req["id"]) or {}).get("sources", [])]
        evidence = [{"id": i, "text": sources[i]["text"]} for i in evidence_ids if i in sources]
        stale_links = [i for i in evidence_ids if i not in sources]
        crit = req.get("criterion")
        if crit and crit["type"] in CHECKS:
            status, basis = CHECKS[crit["type"]](crit, prof)
        elif crit and crit["type"] == "years_experience":
            status, basis = UNKNOWN, "Years of experience need confirmed evidence"
        else:
            status, basis = UNKNOWN, "No comparable criterion; needs confirmed evidence"
        if status == UNKNOWN and evidence:
            status, basis = MET, "User confirmed supporting evidence"
        override = job.get("overrides", {}).get(req["id"])
        if override:
            basis = f"User override: {override['reason']} (computed: {status})"
            status = override["status"]
        results.append({
            "id": req["id"],
            "text": req["text"],
            "category": req["category"],
            "importance": req["importance"],
            "excerpt": req["excerpt"],
            "status": status,
            "basis": basis,
            "evidence": evidence,
            "stale_links": stale_links,
            "overridden": bool(override),
        })
    return results


def summary(results: list[dict]) -> dict:
    counts = {s: 0 for s in STATUSES}
    for r in results:
        counts[r["status"]] += 1
    counts["required_unmet"] = sum(1 for r in results if r["status"] == UNMET and r["importance"] == "required")
    return counts


def link(job_id: str, req_id: str, source_ids: list[str]) -> dict:
    """Record evidence the user confirmed for a requirement."""
    job = jobs_mod.load(job_id)
    jobs_mod.requirement(job, req_id)
    prof = profile_mod.load()
    sources = profile_mod.sources(prof)
    unknown = [s for s in source_ids if s not in sources]
    if unknown:
        raise ResuError(f"Unknown profile source id(s): {', '.join(unknown)}. Use `profile show` to see IDs.")
    if not source_ids:
        raise ResuError("Give at least one profile source id")
    current = (job.setdefault("evidence", {}).get(req_id) or {}).get("sources", [])
    merged = list(dict.fromkeys(current + source_ids))
    job["evidence"][req_id] = {"sources": merged, "confirmed_at": now_iso(), "profile_revision": prof["_meta"]["revision"]}
    jobs_mod.save(job)
    return job


def unlink(job_id: str, req_id: str) -> dict:
    job = jobs_mod.load(job_id)
    jobs_mod.requirement(job, req_id)
    job.get("evidence", {}).pop(req_id, None)
    jobs_mod.save(job)
    return job


def override(job_id: str, req_id: str, status: str, reason: str) -> dict:
    job = jobs_mod.load(job_id)
    jobs_mod.requirement(job, req_id)
    if status == "clear":
        job.get("overrides", {}).pop(req_id, None)
    else:
        if status not in STATUSES:
            raise ResuError(f"Status must be one of {', '.join(STATUSES)} or 'clear'")
        if not reason or not reason.strip():
            raise ResuError("An override needs a reason")
        job.setdefault("overrides", {})[req_id] = {"status": status, "reason": reason.strip(), "at": now_iso()}
    jobs_mod.save(job)
    return job
