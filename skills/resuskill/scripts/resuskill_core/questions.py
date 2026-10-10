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
    r"acknowledge|declaration|signature|sign here|agree to|consent|"
    r"citizen\w*|nationality|national origin|country of (?:birth|origin)|place of birth|"
    r"(?:the age of|aged) \d{2}|\d{2} years old|(?:1[6-9]|2[01]) (?:or|and) (?:older|over|above)|"
    r"(?:over|under|at least|older than|younger than) (?:1[6-9]|2[01])(?! \w)|"
    r"clearance|terminated|fired|dismissed|arrest\w*|"
    r"drug (?:test|screen)\w*|medical condition|health condition|pregnan\w*|caste)\b"
)
_SPONSOR = re.compile(r"\b(sponsor\w*|visa|h-?1b|work permit)\b")
_AUTH = re.compile(
    r"(authori[sz]ed to work|work authori[sz]ation|eligible to work|right to work|"
    r"legally (?:able|permitted|allowed|entitled) to work)"
)
_AUTH_PROMPT = re.compile(
    r"are you (?:legally )?(?:authori[sz]ed|eligible|able|permitted|allowed|entitled) to work"
    r"(?: (?:in .+|for any employer))?"
)
_SPONSOR_PROMPT = re.compile(
    r"(?:will|do) you (?:now or in the future )?(?:require|need) "
    r"(?:visa |employment )?sponsorship(?: (?:now or in the future|to work in .+|in .+))?"
)
# Match entire field labels; a keyword inside a different question is not a field.
_FACTUAL = [
    ("name", r"(?:full |legal )?name"),
    ("email", r"e-?mail(?: address)?"),
    ("phone", r"(?:phone|mobile|telephone)(?: number)?"),
    ("linkedin", r"linkedin(?: (?:url|profile|link))?"),
    ("github", r"github(?: (?:url|profile|link))?"),
    ("portfolio", r"(?:portfolio|personal website|website)(?: (?:url|link))?"),
    ("graduation_date", r"(?:expected )?graduation date"),
    ("start_date", r"(?:earliest )?start date"),
    ("gpa", r"(?:gpa|grade point average)"),
    ("major", r"(?:major|field of study|area of study)"),
    ("location", r"current location"),
]
_RELOCATE = re.compile(r"\breloca\w*\b")
# Deliberately small allow-list. Unrecognised prompts go to the user, including
# arbitrary "what/how/why/describe" questions and compound questions.
_OPEN = re.compile(
    r"(?:why (?:are you interested in|do you want) (?:this|the) (?:role|position|job|internship)|"
    r"why do you want to work (?:here|with us|for us)|"
    r"what interests you about (?:this|the) (?:role|position|job)|"
    r"(?:please )?(?:describe|tell us about) (?:a|an|your) "
    r"(?:relevant |technical |recent |most challenging )?(?:project|work experience|technical challenge)|"
    r"(?:please )?(?:write|provide) a cover letter|cover letter)"
)


def _prompt(text: str) -> str:
    return norm_text(text).rstrip("?.:! ")


# Match the entire location clause after "in", so the pronoun "us" elsewhere
# never selects the US and ambiguous/unknown country wording stays unanswered.
_COUNTRIES = {
    "US": ("united states", "u s", "usa", "america"),
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
    prompt = _prompt(text)
    if _AUTH.search(q):
        return (SENSITIVE_FACTUAL, "authorization") if _AUTH_PROMPT.fullmatch(prompt) else (SENSITIVE, None)
    if _SPONSOR.search(q):
        return (SENSITIVE_FACTUAL, "sponsorship") if _SPONSOR_PROMPT.fullmatch(prompt) else (SENSITIVE, None)
    if _RELOCATE.search(q):
        return UNKNOWN, None
    for key, pattern in _FACTUAL:
        if re.fullmatch(r"(?:(?:what is |please (?:provide|enter) )?(?:your )?)" + pattern, prompt):
            return FACTUAL, key
    if prompt in ("when can you start", "when are you available to start"):
        return FACTUAL, "start_date"
    if prompt in ("where are you located", "where are you currently located", "where are you based"):
        return FACTUAL, "location"
    if _OPEN.fullmatch(prompt):
        return OPEN, None
    return UNKNOWN, None


def draft_refusal(text: str) -> str | None:
    """Why the agent may not draft an answer to this question, or None when it may."""
    detected, _ = classify(text)
    if detected in (SENSITIVE, SENSITIVE_FACTUAL):
        return f"it was detected as {detected}"
    if detected != OPEN:
        return "it is not a recognised open writing prompt; ask the user for their answer"
    return None


def _country(question: str, prof: dict) -> dict | None:
    records = prof.get("authorization") or []
    prompt = _prompt(question)
    places = re.findall(r"\bin\s+(?:the\s+)?(.+)", prompt)
    if places and places[0] != "future":
        place = " ".join(re.findall(r"[a-z0-9]+", places[0]))
        for code, names in _COUNTRIES.items():
            if place in names or (code == "US" and place == "us"):
                return next((r for r in records if r["country"] == code), {"country": code})
        return None  # includes lowercase unknown places and compound country questions
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
