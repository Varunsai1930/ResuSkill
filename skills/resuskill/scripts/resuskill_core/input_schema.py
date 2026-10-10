"""Shape checks at the four JSON input boundaries, before domain validation or writes."""

from __future__ import annotations

import math

from .util import ResuError


def nullable(spec):
    return (type(None), spec)


TEXT = nullable(str)
STRINGS = nullable([str])
BULLET = {"id": TEXT, "text": str}
ENTRY = {k: TEXT for k in (
    "id", "institution", "degree", "field", "gpa", "organization", "title",
    "location", "name", "role", "link", "start", "end", "graduation",
)}
ENTRY.update(technologies=STRINGS, bullets=nullable([(str, BULLET)]))
PROFILE = {
    "contact": nullable({"name": TEXT, "email": TEXT, "phone": TEXT, "location": TEXT,
                         "links": nullable({"*": TEXT})}),
    "summary": TEXT,
    "education": nullable([ENTRY]), "experience": nullable([ENTRY]), "projects": nullable([ENTRY]),
    "skills": nullable([(str, {"name": str, "category": TEXT})]),
    "skills_absent": STRINGS,
    "certifications": nullable([{k: TEXT for k in ("id", "name", "issuer", "date")}]),
    "preferences": nullable({"roles": STRINGS, "locations": STRINGS, "work_mode": TEXT}),
    "availability": nullable({"start_date": TEXT, "notes": TEXT}),
    "authorization": nullable([{"country": str, "authorized": nullable(bool),
                                "requires_sponsorship": nullable(bool)}]),
    "_meta": dict,  # emitted metadata is ignored on input, never trusted as counters
}
DRAFT_TEXT = {"text": str, "sources": [str]}
RESUME = {
    "summary": nullable(DRAFT_TEXT),
    "experience": nullable([{"entry": str, "bullets": [DRAFT_TEXT]}]),
    "projects": nullable([{"entry": str, "bullets": [DRAFT_TEXT]}]),
    "education": STRINGS, "certifications": STRINGS, "skills": STRINGS,
}
ANSWERS = [{"question_id": str, "text": str, "sources": [str], "bank_id": TEXT}]
CRITERION = {
    "type": str, "skills": STRINGS, "match": str, "level": str, "fields": STRINGS,
    "status": str, "from": TEXT, "to": TEXT, "locations": STRINGS, "work_mode": TEXT,
    "country": str, "sponsorship_available": nullable(bool), "start_by": TEXT,
    "start_from": TEXT, "years": (int, float), "area": TEXT,
}
REQUIREMENTS = [{"id": TEXT, "text": str, "excerpt": str, "category": str,
                 "importance": str, "criterion": nullable(CRITERION)}]


def _describe(spec):
    if isinstance(spec, tuple):
        return " or ".join(_describe(s) for s in spec)
    if isinstance(spec, dict):
        return "an object with " + ", ".join(spec)
    if isinstance(spec, list):
        return "a list of " + _describe(spec[0])
    return {str: "text", bool: "true/false", int: "a number", float: "a number",
            type(None): "null", dict: "an object"}[spec]


def _errors(value, spec, path):
    if isinstance(spec, tuple):
        if any(not _errors(value, choice, path) for choice in spec):
            return []
        # Keep nested paths for a matching container type.
        for choice in spec:
            if isinstance(choice, dict) and isinstance(value, dict):
                return _errors(value, choice, path)
            if isinstance(choice, list) and isinstance(value, list):
                return _errors(value, choice, path)
    elif isinstance(spec, dict) and isinstance(value, dict):
        errors = []
        for key, item in value.items():
            if key in spec or "*" in spec:
                errors.extend(_errors(item, spec.get(key, spec.get("*")), f"{path}.{key}"))
            else:
                errors.append(f"{path}.{key}: unknown field; expected {', '.join(spec)}")
        return errors
    elif isinstance(spec, list) and isinstance(value, list):
        return [e for i, item in enumerate(value) for e in _errors(item, spec[0], f"{path}[{i}]")]
    elif isinstance(spec, type) and type(value) is spec:
        if spec is float and not math.isfinite(value):
            return [f"{path}: number must be finite"]
        return []
    return [f"{path} must be {_describe(spec)}"]


def check(value, spec, name):
    errors = _errors(value, spec, name)
    if errors:
        raise ResuError(f"Invalid {name} JSON; nothing was saved.", errors)

