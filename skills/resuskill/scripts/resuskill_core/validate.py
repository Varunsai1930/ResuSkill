"""Fabrication checks for agent-written resume proposals and answer drafts.

Every generated sentence must cite profile sources. A sentence is rejected when it
introduces numbers, years, technologies or credentials that its sources do not contain.
These checks are a safety net, not proof of accuracy; the user still reviews meaning.
"""

from __future__ import annotations

import re

from . import profile as profile_mod
from .skills import canon, display, find_terms
from .util import ResuError, norm_text

_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.])[$€£₹]?(\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)")
_NUMBER_WORDS = {
    "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "dozen": "12",
    "thirteen": "13", "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40",
    "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
    "hundred": "100", "thousand": "1000", "million": "1000000", "billion": "1000000000",
    "twice": "2", "doubled": "2", "tripled": "3",
    "quadrupled": "4", "halved": "0.5", "tenfold": "10",
}
# A trailing "s" covers scale words used loosely: "hundreds", "thousands", "millions", "dozens".
_WORD_RE = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")s?\b", re.IGNORECASE)

# Credential-like claims, grouped so different spellings compare equal.
_CREDENTIALS = {
    "certification": r"certif(?:ied|ication|icate)s?",
    "license": r"licen[cs](?:e|ed|es|ing)",
    "patent": r"patent(?:s|ed)?",
    "award": r"award(?:s|ed|-winning)?",
    "doctorate": r"ph\.?\s?d\.?|doctorate|doctoral",
    "degree": r"degree|bachelor'?s|master'?s|mba",
    "professional credential": r"\b(?:cpa|pmp|cfa|cissp|ccna)\b",
    "publication": r"publish(?:ed|ing)?|publications?|peer[- ]reviewed",
    "honor": r"cum laude|dean'?s list|scholarship|fellowship|valedictorian",
}
_CREDENTIAL_RES = {name: re.compile(rf"(?<!\w)(?:{pat})(?!\w)", re.IGNORECASE) for name, pat in _CREDENTIALS.items()}


def numbers(text: str) -> set[str]:
    found = set()
    for match in _NUMBER_RE.finditer(text or ""):
        raw = match.group(1).replace(",", "")
        if "." in raw:
            raw = raw.rstrip("0").rstrip(".") or "0"
        found.add(raw.lstrip("0") or "0")
    for match in _WORD_RE.finditer(text or ""):
        found.add(_NUMBER_WORDS[match.group(1).lower()])
    return found


def credentials(text: str) -> set[str]:
    return {name for name, regex in _CREDENTIAL_RES.items() if regex.search(text or "")}


def claim_problems(text: str, source_texts: list[str], allowed_tech: set[str], extra_terms) -> list[str]:
    """Problems with ``text`` relative to the cited sources."""
    joined = "\n".join(source_texts)
    problems = []
    new_numbers = numbers(text) - numbers(joined)
    if new_numbers:
        problems.append(f"numbers/years not in its sources: {', '.join(sorted(new_numbers))}")
    tech = find_terms(text, extra_terms) - find_terms(joined, extra_terms) - allowed_tech
    if tech:
        problems.append(f"technologies not in its sources: {', '.join(display(t) for t in sorted(tech))}")
    creds = credentials(text) - credentials(joined)
    if creds:
        problems.append(f"credential claims not in its sources: {', '.join(sorted(creds))}")
    return problems


def detection_terms(prof: dict, job: dict | None) -> tuple[str, ...]:
    """Extra terms for technology detection beyond the built-in lexicon."""
    terms = [s["name"] for s in prof.get("skills") or []] + list(prof.get("skills_absent") or [])
    for section in ("experience", "projects"):
        for entry in prof.get(section) or []:
            terms.extend(entry.get("technologies") or [])
    if job:
        for req in job.get("requirements") or []:
            crit = req.get("criterion") or {}
            if crit.get("type") == "skill":
                terms.extend(crit["skills"])
    return tuple(sorted(set(terms)))


def _sources_list(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return []


def validate_proposal(prof: dict, job: dict, proposal) -> tuple[dict, list[str]]:
    """Validate a resume proposal. Returns (clean proposal, warnings); raises on errors."""
    if not isinstance(proposal, dict):
        raise ResuError("Proposal must be a JSON object")
    sources = profile_mod.sources(prof)
    extra = detection_terms(prof, job)
    profile_skills = profile_mod.skill_keys(prof)
    errors: list[str] = []
    warnings: list[str] = []
    clean: dict = {}

    summary = proposal.get("summary")
    if summary:
        if isinstance(summary, str):
            summary = {"text": summary, "sources": []}
        text = str(summary.get("text", "")).strip()
        cited = _sources_list(summary.get("sources"))
        missing = [s for s in cited if s not in sources]
        if not cited:
            errors.append("summary: cite at least one profile source")
        if missing:
            errors.append(f"summary: unknown sources {', '.join(missing)}")
        else:
            for problem in claim_problems(text, [sources[s]["text"] for s in cited], profile_skills, extra):
                errors.append(f"summary: {problem}")
        clean["summary"] = {"text": text, "sources": cited}

    for section in ("experience", "projects"):
        section_out = []
        seen_entries: set[str] = set()
        items = proposal.get(section) or []
        if not isinstance(items, list):
            errors.append(f"{section} must be a list")
            continue
        for index, item in enumerate(items):
            where = f"{section}[{index}]"
            entry_id = str((item or {}).get("entry", "")).strip()
            found = profile_mod.entry_by_id(prof, entry_id)
            if not found or found[0] != section:
                errors.append(f"{where}: {entry_id!r} is not a {section} entry in the profile")
                continue
            if entry_id in seen_entries:
                errors.append(f"{where}: entry {entry_id} appears twice")
                continue
            seen_entries.add(entry_id)
            entry = found[1]
            entry_tech = {canon(t) for t in entry.get("technologies") or []}
            bullets_out = []
            for b_index, bullet in enumerate(item.get("bullets") or []):
                b_where = f"{where}.bullets[{b_index}]"
                if isinstance(bullet, str) or not isinstance(bullet, dict):
                    errors.append(f"{b_where}: must be an object with text and sources")
                    continue
                text = str(bullet.get("text", "")).strip()
                cited = _sources_list(bullet.get("sources"))
                if not text:
                    errors.append(f"{b_where}: empty text")
                    continue
                if not cited:
                    errors.append(f"{b_where}: cite at least one source bullet from {entry_id}")
                    continue
                bad = [s for s in cited if s not in sources]
                foreign = [s for s in cited if s in sources and sources[s]["entry"] != entry_id]
                if bad:
                    errors.append(f"{b_where}: unknown sources {', '.join(bad)}")
                    continue
                if foreign:
                    errors.append(f"{b_where}: sources {', '.join(foreign)} belong to a different entry than {entry_id}")
                    continue
                for problem in claim_problems(text, [sources[s]["text"] for s in cited], entry_tech, extra):
                    errors.append(f"{b_where}: {problem} — {text[:70]!r}")
                if len(text) > 350:
                    warnings.append(f"{b_where}: long bullet ({len(text)} characters)")
                bullets_out.append({"text": text, "sources": cited})
            if not bullets_out:
                warnings.append(f"{where}: {entry_id} has no bullets")
            section_out.append({"entry": entry_id, "bullets": bullets_out})
        clean[section] = section_out

    edu_ids = [e["id"] for e in prof.get("education") or []]
    education = proposal.get("education")
    if education is None:
        clean["education"] = edu_ids
    else:
        bad = [e for e in education if e not in edu_ids]
        if bad:
            errors.append(f"education: unknown entries {', '.join(map(str, bad))}")
        clean["education"] = [e for e in dict.fromkeys(education) if e in edu_ids]

    cert_ids = [c["id"] for c in prof.get("certifications") or []]
    certs = proposal.get("certifications")
    if certs is None:
        clean["certifications"] = cert_ids
    else:
        bad = [c for c in certs if c not in cert_ids]
        if bad:
            errors.append(f"certifications: unknown entries {', '.join(map(str, bad))}")
        clean["certifications"] = [c for c in dict.fromkeys(certs) if c in cert_ids]

    skills = proposal.get("skills")
    if skills is None:
        clean["skills"] = [s["name"] for s in prof.get("skills") or []]
    else:
        names = []
        for name in skills:
            if canon(str(name)) not in profile_skills:
                errors.append(f"skills: {name!r} is not in the profile")
            elif canon(str(name)) not in {canon(n) for n in names}:
                names.append(display(str(name)))
        clean["skills"] = names

    if not clean.get("experience") and not clean.get("projects"):
        warnings.append("Proposal includes no experience or projects")
    if errors:
        raise ResuError("Proposal rejected; nothing was stored. Fix these and propose again.", errors)
    return clean, warnings


def check_length(text: str, limit: int | None, unit: str) -> str | None:
    if not limit:
        return None
    size = len(text.split()) if unit == "words" else len(text)
    if size > limit:
        return f"{size} {unit} exceeds the limit of {limit}"
    return None


def validate_answer(prof: dict, job: dict, text: str, cited: list[str], limit: int | None, unit: str) -> list[str]:
    """Errors for an AI-drafted answer."""
    sources = profile_mod.sources(prof)
    errors = []
    if not text.strip():
        errors.append("empty answer")
    bad = [s for s in cited if s not in sources]
    if bad:
        errors.append(f"unknown sources {', '.join(bad)}")
    else:
        problems = claim_problems(
            text,
            [sources[s]["text"] for s in cited] + [prof.get("summary") or ""],
            profile_mod.skill_keys(prof),
            detection_terms(prof, job),
        )
        errors.extend(problems)
    length = check_length(text, limit, unit)
    if length:
        errors.append(length)
    return errors


def originals(prof: dict, cited: list[str]) -> str:
    sources = profile_mod.sources(prof)
    return " | ".join(sources[s]["text"] for s in cited if s in sources)


def same_text(a: str, b: str) -> bool:
    return norm_text(a) == norm_text(b)
