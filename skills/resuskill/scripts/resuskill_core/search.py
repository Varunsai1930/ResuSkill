"""Job-search terms derived from the profile.

Read-only and offline: this builds queries for the agent's own web search tool. It never
includes contact details, so queries do not reveal who the user is.
"""

from __future__ import annotations

import re

from . import profile as profile_mod
from .skills import canon, display, find_terms
from .util import ResuError, date_span, norm_text, today_key

QUERY_SKILLS = 3


def _unique(values) -> list[str]:
    seen, result = set(), []
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if text and norm_text(text) not in seen:
            seen.add(norm_text(text))
            result.append(text)
    return result


def _roles(prof: dict, requested: list[str]) -> tuple[list[str], str]:
    if requested:
        return _unique(requested), "request"
    preferred = _unique((prof.get("preferences") or {}).get("roles") or [])
    if preferred:
        return preferred, "preferences"
    titles = _unique(e.get("title") for e in prof.get("experience") or [])
    return titles[:2], "experience titles" if titles else "none"


def ranked_skills(prof: dict) -> list[dict]:
    """Confirmed skills, most evidenced first. Evidence = experience/project entries using the skill."""
    names: dict[str, str] = {}
    for s in prof.get("skills") or []:
        names.setdefault(canon(s["name"]), display(s["name"]))
    for section in ("experience", "projects"):
        for entry in prof.get(section) or []:
            for tech in entry.get("technologies") or []:
                names.setdefault(canon(tech), display(tech))
    absent = {canon(s) for s in prof.get("skills_absent") or []}
    extra = tuple(names.values())
    counts = dict.fromkeys(names, 0)
    for section in ("experience", "projects"):
        for entry in prof.get(section) or []:
            text = " ".join(b["text"] for b in entry.get("bullets") or [])
            used = {canon(t) for t in entry.get("technologies") or []} | find_terms(text, extra)
            for key in used & counts.keys():
                counts[key] += 1
    order = list(names)
    ranked = sorted((k for k in order if k not in absent), key=lambda k: (-counts[k], order.index(k)))
    return [{"name": names[k], "evidence_count": counts[k]} for k in ranked]


def _level(prof: dict) -> dict:
    grad = profile_mod.graduation_date(prof)
    span = date_span(grad) if grad else None
    if not span:
        return {"hint": None, "basis": "graduation date unknown; ask the user which level to search"}
    today = today_key()
    if span[0] > today:
        return {"hint": "student", "basis": f"expected graduation {grad}"}
    year_ago = (today[0] - 1, today[1], today[2])
    if span[1] >= year_ago:
        return {"hint": "recent graduate", "basis": f"graduated {grad}"}
    return {"hint": None, "basis": f"graduated {grad}; ask the user which level to search"}


_LEVEL_TERMS = {"student": "intern OR entry level", "recent graduate": "entry level"}
_LEVEL_WORDS = re.compile(r"\b(intern|internship|co-?op|new grad|entry[- ]level|junior|senior|lead|principal|staff)\b", re.I)


def terms(requested_roles=None, locations=None, max_queries: int = 6, query_skills=None) -> dict:
    prof = profile_mod.load()
    prefs = prof.get("preferences") or {}
    roles, role_source = _roles(prof, requested_roles or [])
    skills = ranked_skills(prof)
    work_mode = prefs.get("work_mode")
    places = _unique(locations or prefs.get("locations") or [(prof.get("contact") or {}).get("location")])
    if work_mode in ("remote", "any") and "remote" not in {norm_text(p) for p in places}:
        places.append("Remote")
    level = _level(prof)
    warnings = []
    if not roles:
        warnings.append("No target roles: ask the user which roles to search for, or add preferences.roles")
    elif role_source == "experience titles":
        warnings.append("No preferences.roles; roles come from past job titles. Confirm them with the user")
    if not skills:
        warnings.append("No confirmed skills in the profile; queries use roles only")
    if not places:
        warnings.append("No location preference or contact location; ask the user where to search")
    if work_mode is None:
        warnings.append("Work mode unknown; ask the user whether remote roles count")

    if query_skills:
        by_key = {canon(s["name"]): s["name"] for s in skills}
        unknown = [s for s in query_skills if canon(s) not in by_key]
        if unknown:
            raise ResuError("Query skills must be confirmed profile skills", [f"not in profile: {s}" for s in unknown])
        chosen = _unique(by_key[canon(s)] for s in query_skills)
    else:
        chosen = [s["name"] for s in skills[:QUERY_SKILLS]]
    top = " ".join(chosen)
    queries = []
    for role in roles:
        suffix = "" if _LEVEL_WORDS.search(role) else _LEVEL_TERMS.get(level["hint"], "")
        for place in places or [""]:
            parts = [f'"{role}"', suffix, top, place]
            queries.append(" ".join(p for p in parts if p))
    return {
        "roles": roles,
        "role_source": role_source,
        "skills": skills,
        "query_skills": chosen,
        "locations": places,
        "work_mode": work_mode,
        "level": level,
        "skills_absent": list(prof.get("skills_absent") or []),
        "sponsorship_needed": [a["country"] for a in prof.get("authorization") or [] if a.get("requires_sponsorship") is True],
        "authorization_unknown": [a["country"] for a in prof.get("authorization") or []
                                  if a.get("authorized") is None or a.get("requires_sponsorship") is None],
        "queries": queries[:max(1, max_queries)],
        "warnings": warnings,
    }
