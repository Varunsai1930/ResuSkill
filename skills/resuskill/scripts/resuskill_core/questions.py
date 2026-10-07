"""Application questions: rule-based categories, profile-backed factual values, answer bank."""

from __future__ import annotations

import re

from . import profile as profile_mod
from . import store
from .util import ResuError, norm_text, now_iso

FACTUAL, SENSITIVE_FACTUAL, SENSITIVE, OPEN, UNKNOWN = "factual", "sensitive_factual", "sensitive", "open", "unknown"
CATEGORIES = (FACTUAL, SENSITIVE_FACTUAL, SENSITIVE, OPEN, UNKNOWN)

_SENSITIVE = re.compile(
    r"\b(gender|sex|pronouns?|race|racial|ethnic\w*|hispanic|latin[oax]|veterans?|military status|"
    r"disabilit\w*|disabled|sexual orientation|lgbtq?\w*|transgender|religio\w*|marital|date of birth|"
    r"age|how old|criminal|convicted|conviction|felony|misdemeanou?r|background check|salary|"
    r"compensation|pay expectations?|desired pay|expected pay|current pay|attest\w*|certify that|"
    r"acknowledge|declaration|signature|sign here|agree to|consent)\b"
)
_SPONSOR = re.compile(r"\b(sponsor\w*|visa|h-?1b|work permit)\b")
_AUTH = re.compile(
    r"(authori[sz]ed to work|work authori[sz]ation|eligible to work|right to work|"
    r"legally (?:able|permitted|allowed|entitled) to work)"
)
_FACTUAL = [
    ("name", re.compile(r"\b(full name|first name|last name|legal name|your name|preferred name)\b")),
    ("email", re.compile(r"\be-?mail\b")),
    ("phone", re.compile(r"\b(phone|mobile|telephone)\b")),
    ("linkedin", re.compile(r"\blinkedin\b")),
    ("github", re.compile(r"\bgithub\b")),
    ("portfolio", re.compile(r"\b(portfolio|personal website|website)\b")),
    ("graduation_date", re.compile(r"\bgraduat\w*\b")),
    ("start_date", re.compile(r"\b(start date|available to start|earliest start|when can you start|availability)\b")),
    ("gpa", re.compile(r"\b(gpa|grade point)\b")),
    ("major", re.compile(r"\b(major|field of study|area of study)\b")),
    ("degree", re.compile(r"\bdegree\b")),
    ("school", re.compile(r"\b(school|university|college|institution)\b")),
    ("location", re.compile(r"\b(where are you (?:currently )?(?:located|based)|current location|city|location)\b")),
]
_RELOCATE = re.compile(r"\breloca\w*\b")
_OPEN = re.compile(
    r"^(why|what|how|describe|tell us|explain|share|walk us|give an example|please describe)\b|"
    r"\bwhy\b|tell us about|describe|cover letter|anything else|interest(?:s|ed)? you"
)
# Matched as whole words after reducing the question to lowercase words ("U.S." -> "u s").
_COUNTRIES = {
    "US": ("united states", "u s", "us", "usa", "america"),
    "CA": ("canada",),
    "GB": ("united kingdom", "uk", "britain", "england"),
    "IN": ("india",),
    "DE": ("germany",),
    "AU": ("australia",),
    "IE": ("ireland",),
    "SG": ("singapore",),
    "NL": ("netherlands",),
}


def classify(text: str) -> tuple[str, str | None]:
    """Return (category, factual key) using explicit keyword rules."""
    q = norm_text(text)
    if _SENSITIVE.search(q):
        return SENSITIVE, None
    if _SPONSOR.search(q) and re.search(r"\b(require|need|will you|do you)\b", q):
        return SENSITIVE_FACTUAL, "sponsorship"
    if _AUTH.search(q):
        return SENSITIVE_FACTUAL, "authorization"
    if _SPONSOR.search(q):
        return SENSITIVE_FACTUAL, "sponsorship"
    if _RELOCATE.search(q):
        return UNKNOWN, None
    for key, regex in _FACTUAL:
        if regex.search(q):
            return FACTUAL, key
    if _OPEN.search(q):
        return OPEN, None
    return UNKNOWN, None


_NAMED_PLACE = re.compile(r"\bin\s+(?:the\s+)?[A-Z]")


def _country(question: str, prof: dict) -> dict | None:
    records = prof.get("authorization") or []
    words = " " + " ".join(re.findall(r"[a-z0-9]+", norm_text(question))) + " "
    for code, names in _COUNTRIES.items():
        if any(f" {name} " in words for name in names):
            return next((r for r in records if r["country"] == code), {"country": code})
    if _NAMED_PLACE.search(question):
        return None  # names a place we cannot map; never answer it from another country's record
    return records[0] if len(records) == 1 else None


def _yes_no(value) -> str | None:
    return {True: "Yes", False: "No"}.get(value)


def factual_value(key: str, question: str, prof: dict) -> str | None:
    """The profile's value for a factual question, or None when missing."""
    contact = prof.get("contact") or {}
    links = contact.get("links") or {}
    education = sorted(prof.get("education") or [], key=lambda e: e.get("graduation") or e.get("end") or "", reverse=True)
    latest = education[0] if education else {}
    if key in ("name", "email", "phone", "location"):
        return contact.get(key) or None
    if key in ("linkedin", "github", "portfolio"):
        return links.get(key) or None
    if key == "graduation_date":
        return profile_mod.graduation_date(prof)
    if key == "start_date":
        return (prof.get("availability") or {}).get("start_date") or None
    if key == "school":
        return latest.get("institution") or None
    if key == "degree":
        return latest.get("degree") or None
    if key == "major":
        return latest.get("field") or None
    if key == "gpa":
        return latest.get("gpa") or None
    if key == "authorization":
        record = _country(question, prof)
        return _yes_no(record.get("authorized")) if record else None
    if key == "sponsorship":
        record = _country(question, prof)
        return _yes_no(record.get("requires_sponsorship")) if record else None
    return None


# ---------------------------------------------------------------- answer bank

def bank() -> list[dict]:
    return store.read_json(store.bank_path(), default=[])


def bank_save(question: str, text: str, origin: str) -> dict:
    if not text.strip():
        raise ResuError("Only non-empty accepted answers can be saved to the bank")
    items = bank()
    entry = {"id": f"bank-{len(items) + 1}", "question": question, "text": text, "origin": origin, "saved_at": now_iso()}
    items.append(entry)
    store.write_json(store.bank_path(), items)
    return entry
