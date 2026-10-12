"""Job-search terms derived from the profile.

Read-only and offline: this builds queries for the agent's own web search tool. It never
includes contact details, so queries do not reveal who the user is.
"""

from __future__ import annotations

import re

from . import jobs as jobs_mod
from . import profile as profile_mod
from .skills import canon, display, find_terms
from .util import ResuError, date_key, date_span, norm_text, today_key

QUERY_SKILLS = 3

# Using one of these in an entry is evidence of an already confirmed broader skill. Ranking only:
# this never adds a skill the profile does not list.
_IMPLIES = {canon(name): canon("SQL") for name in (
    "PostgreSQL", "MySQL", "SQLite", "SQL Server", "Microsoft SQL Server", "T-SQL", "MariaDB",
    "Oracle", "BigQuery", "Snowflake", "Redshift")}


def _unique(values) -> list[str]:
    seen, result = set(), []
    for value in values:
        text = re.sub(r"\s+", " ", re.sub(r'["\u201c\u201d\u201e\u201f\u2033]', " ", str(value or ""))).strip()
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
    # Most recent first: ongoing roles, then by end date, then by start date.
    def recency(entry):
        return (entry.get("end") == "present",
                date_key(entry.get("end"), end_of_period=True) or date_key(entry.get("start")) or (0, 0, 0),
                date_key(entry.get("start")) or (0, 0, 0))
    recent = sorted(prof.get("experience") or [], key=recency, reverse=True)
    titles = _unique(e.get("title") for e in recent)
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
            used |= {_IMPLIES[k] for k in used if k in _IMPLIES}
            for key in used & counts.keys():
                counts[key] += 1
    order = {k: i for i, k in enumerate(names)}
    ranked = sorted((k for k in names if k not in absent), key=lambda k: (-counts[k], order[k]))
    return [{"name": names[k], "evidence_count": counts[k]} for k in ranked]


def _level(prof: dict) -> dict:
    grad = profile_mod.graduation_date(prof)
    span = date_span(grad) if grad else None
    if not span:
        return {"hint": None, "basis": "graduation date unknown; ask the user which level to search"}
    today = today_key()
    if span[0] <= today <= span[1]:
        return {"hint": None, "basis": f"graduation date {grad} does not establish completion; ask the user which level to search"}
    # A further degree, whether ongoing or recently completed, does not establish career level.
    # High school and associate degrees before a transfer do not suppress a first-degree hint.
    finished = [date_span(e.get("graduation") or e.get("end")) for e in prof.get("education") or []
                if (jobs_mod.degree_level(e.get("degree", "")) or 0) >= 1]
    if any(sp and sp[1] < min(today, span[0]) for sp in finished):
        return {"hint": None, "basis": f"additional degree dated {grad} after a completed one; ask the user which level to search"}
    if span[0] > today:
        return {"hint": "student", "basis": f"expected graduation {grad}"}
    year_ago = (today[0] - 1, today[1], today[2])
    if span[1] >= year_ago:
        return {"hint": "recent graduate", "basis": f"graduated {grad}"}
    return {"hint": None, "basis": f"graduated {grad}; ask the user which level to search"}


_COUNTRIES = {"US": "United States", "CA": "Canada", "GB": "United Kingdom", "UK": "United Kingdom",
              "IE": "Ireland", "AU": "Australia", "NZ": "New Zealand", "IN": "India", "DE": "Germany",
              "FR": "France", "NL": "Netherlands", "ES": "Spain", "SG": "Singapore", "JP": "Japan"}


def _remote_places(prof: dict) -> list[str]:
    """"Remote <country>" for each country the user is authorized to work in; plain "Remote" if none is known.

    A bare "Remote" query returns postings from anywhere, most of which the user cannot take.
    """
    countries = [a["country"] for a in prof.get("authorization") or [] if a.get("authorized") is True]
    return [f"Remote {_COUNTRIES.get(c, c)}" for c in countries] or ["Remote"]


LEVELS = ("student", "intern", "entry", "junior", "mid", "senior", "lead", "manager", "director", "any")
_LEVEL_TERMS = {"student": 'intern OR "entry level"', "recent graduate": '"entry level"',
                "intern": "intern", "entry": '"entry level"', "junior": "junior", "mid": '"mid level"',
                "senior": "senior", "lead": "lead", "manager": "manager", "director": "director"}
_LEVEL_WORDS = re.compile(
    r"\b(intern|internship|co-?op|new grad|entry[- ]level|junior|mid[- ]level|senior|lead|principal|staff|"
    r"manager|director|head|executive|vp|vice president)\b", re.I)


def terms(requested_roles=None, locations=None, max_queries: int = 6, query_skills=None, level=None) -> dict:
    if max_queries < 1:
        raise ResuError("--max-queries must be at least 1")
    if level is not None and level not in LEVELS:
        raise ResuError("Unknown search level", [f"choose one of: {', '.join(LEVELS)}"])
    level_requested = level is not None
    prof = profile_mod.load()
    prefs = prof.get("preferences") or {}
    roles, role_source = _roles(prof, requested_roles or [])
    skills = ranked_skills(prof)
    work_mode = prefs.get("work_mode")
    if locations:
        places = _unique(locations)  # the user's request: search exactly these
    elif work_mode == "remote":
        places = _remote_places(prof)
    else:
        places = _unique(prefs.get("locations") or [])
        if work_mode == "any" and not any(norm_text(p).startswith("remote") for p in places):
            places.extend(_remote_places(prof))
    level = ({"hint": None if level == "any" else level, "basis": f"requested level: {level}"}
             if level_requested else _level(prof))
    warnings = []
    if not roles:
        warnings.append("No target roles: ask the user which roles to search for, or add preferences.roles")
    elif role_source == "experience titles":
        warnings.append("No preferences.roles; roles come from past job titles. Confirm them with the user")
    if not skills:
        warnings.append("No confirmed skills in the profile; queries use roles only")
    if not places or (not locations and not prefs.get("locations") and work_mode != "remote"):
        warnings.append("No location preference; ask the user for a search city/region or pass --location")
    if work_mode is None:
        warnings.append("Work mode unknown; ask the user whether remote roles count")
    if not level_requested and level["hint"] is None and any(not _LEVEL_WORDS.search(role) for role in roles):
        warnings.append(level["basis"])

    if query_skills:
        by_key = {canon(s["name"]): s["name"] for s in skills}
        unknown = [s for s in query_skills if canon(s) not in by_key]
        if unknown:
            raise ResuError("Query skills must be confirmed profile skills", [f"not in profile: {s}" for s in unknown])
        chosen = _unique(by_key[canon(s)] for s in query_skills)
    else:
        chosen = [s["name"] for s in skills[:QUERY_SKILLS]]
    top = " ".join(chosen)
    # Diagonal order over (place, role) pairs so a query cap still covers every role and place
    # as far as the cap allows, instead of dropping the last role or place (often Remote) whole.
    pairs = [(i, j) for i in range(len(places or [""])) for j in range(len(roles))]
    pairs.sort(key=lambda ij: (ij[0] + ij[1], ij[0]))  # within a diagonal, new roles before new places
    queries = []
    for i, j in pairs:
        role, place = roles[j], (places or [""])[i]
        suffix = "" if _LEVEL_WORDS.search(role) else _LEVEL_TERMS.get(level["hint"], "")
        remote = "Remote" if work_mode == "remote" and not re.search(r"\bremote\b", place, re.I) else ""
        queries.append(" ".join(p for p in (f'"{role}"', suffix, top, place, remote) if p))
    if len(queries) > max_queries:
        warnings.append(f"{len(queries) - max_queries} queries left out by --max-queries {max_queries}; "
                        "raise it or narrow roles/locations to search them")
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
        "queries": queries[:max_queries],
        "warnings": warnings,
    }
