"""The canonical candidate profile: template, validation, stable IDs, diff and save.

Only the user decides what goes into the profile. The agent proposes a JSON file,
shows `profile diff` to the user, and runs `profile save` after the user confirms.
"""

from __future__ import annotations

import copy
import re

from . import SCHEMA_VERSION, store
from .skills import canon, display
from .util import ResuError, is_valid_date, norm_text, now_iso

ENTRY_SECTIONS = {"education": "edu", "experience": "exp", "projects": "proj"}
WORK_MODES = {"remote", "hybrid", "onsite", "any", None}

TEMPLATE = {
    "contact": {
        "name": "",
        "email": "",
        "phone": "",
        "location": "",
        "links": {"linkedin": "", "github": "", "portfolio": ""},
    },
    "summary": "",
    "education": [
        {
            "institution": "",
            "degree": "e.g. B.S.",
            "field": "e.g. Computer Science",
            "start": "YYYY-MM",
            "end": "YYYY-MM (expected end for current students)",
            "gpa": "",
            "bullets": [],
        }
    ],
    "experience": [
        {
            "organization": "",
            "title": "",
            "location": "",
            "start": "YYYY-MM",
            "end": "YYYY-MM or present",
            "technologies": [],
            "bullets": ["One accomplishment per bullet, exactly as the user confirms it."],
        }
    ],
    "projects": [
        {
            "name": "",
            "role": "",
            "link": "",
            "start": "YYYY-MM",
            "end": "YYYY-MM or present",
            "technologies": [],
            "bullets": [],
        }
    ],
    "skills": [{"name": "Python", "category": "Languages"}],
    "skills_absent": [],
    "certifications": [{"name": "", "issuer": "", "date": "YYYY-MM"}],
    "preferences": {"roles": [], "locations": [], "work_mode": "any"},
    "availability": {"start_date": "YYYY-MM", "notes": ""},
    "authorization": [
        {"country": "US", "authorized": None, "requires_sponsorship": None}
    ],
}


def load(required: bool = True) -> dict | None:
    data = store.read_json(store.profile_path())
    if data is None and required:
        raise ResuError("No profile saved yet. Create one with `profile template` and `profile save`.")
    return data


def revision() -> int:
    data = load(required=False)
    return int(data["_meta"]["revision"]) if data else 0


# ---------------------------------------------------------------- validation

def _as_list(value, field: str, errors: list[str]) -> list:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be a list")
        return []
    return value


def _clean_str(value) -> str:
    return value.strip() if isinstance(value, str) else ("" if value is None else str(value))


def _entry_key(section: str, entry: dict) -> str:
    if section == "education":
        parts = (entry.get("institution"), entry.get("degree"))
    elif section == "experience":
        parts = (entry.get("organization"), entry.get("title"), entry.get("start"))
    else:
        parts = (entry.get("name"),)
    return "|".join(norm_text(_clean_str(p)) for p in parts)


def _next_id(counters: dict, prefix: str) -> str:
    counters[prefix] = counters.get(prefix, 0) + 1
    return f"{prefix}-{counters[prefix]}"


def _seed_counters(*profiles) -> dict:
    counters: dict[str, int] = {}
    for prof in profiles:
        if not prof:
            continue
        for prefix, value in prof.get("_meta", {}).get("id_counters", {}).items():
            counters[prefix] = max(counters.get(prefix, 0), int(value))
        for section, prefix in ENTRY_SECTIONS.items():
            for entry in prof.get(section) or []:
                if not isinstance(entry, dict):
                    continue
                match = re.fullmatch(rf"{prefix}-(\d+)", str(entry.get("id", "")))
                if match:
                    counters[prefix] = max(counters.get(prefix, 0), int(match.group(1)))
        for cert in prof.get("certifications") or []:
            match = re.fullmatch(r"cert-(\d+)", str((cert or {}).get("id", "")))
            if match:
                counters["cert"] = max(counters.get("cert", 0), int(match.group(1)))
    return counters


def _bullet_counter(entry_id: str, *entries) -> int:
    best = 0
    for entry in entries:
        for bullet in (entry or {}).get("bullets") or []:
            if isinstance(bullet, dict):
                match = re.fullmatch(rf"{re.escape(entry_id)}-b(\d+)", str(bullet.get("id", "")))
                if match:
                    best = max(best, int(match.group(1)))
    return best


def normalize(data: dict, current: dict | None = None) -> tuple[dict, list[str]]:
    """Validate a proposed profile and assign stable IDs. Returns (profile, warnings)."""
    if not isinstance(data, dict):
        raise ResuError("Profile must be a JSON object")
    errors: list[str] = []
    warnings: list[str] = []
    current = current or {}
    prof = copy.deepcopy(data)
    prof.pop("_meta", None)
    counters = _seed_counters(current, data)

    contact = prof.get("contact") or {}
    if not isinstance(contact, dict):
        errors.append("contact must be an object")
        contact = {}
    contact = {k: _clean_str(contact.get(k)) for k in ("name", "email", "phone", "location")} | {
        "links": {str(k): _clean_str(v) for k, v in (contact.get("links") or {}).items() if _clean_str(v)}
    }
    if not contact["name"]:
        errors.append("contact.name is required")
    if contact["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", contact["email"]):
        errors.append(f"contact.email looks invalid: {contact['email']!r}")
    prof["contact"] = contact
    prof["summary"] = _clean_str(prof.get("summary"))

    seen_ids: set[str] = set()
    for section, prefix in ENTRY_SECTIONS.items():
        current_by_id = {e.get("id"): e for e in current.get(section) or [] if isinstance(e, dict)}
        current_by_key = {_entry_key(section, e): e for e in current_by_id.values()}
        entries = []
        for index, raw in enumerate(_as_list(prof.get(section), section, errors)):
            where = f"{section}[{index}]"
            if not isinstance(raw, dict):
                errors.append(f"{where} must be an object")
                continue
            entry = {k: v for k, v in raw.items()}
            for field in ("start", "end", "graduation"):
                if field in entry:
                    entry[field] = _clean_str(entry[field]).lower() if _clean_str(entry[field]).lower() == "present" else _clean_str(entry[field])
                    if not is_valid_date(entry[field]):
                        errors.append(f"{where}.{field} must be YYYY, YYYY-MM, YYYY-MM-DD or 'present' (got {entry[field]!r})")
            name_field = {"education": "institution", "experience": "organization", "projects": "name"}[section]
            if not _clean_str(entry.get(name_field)):
                errors.append(f"{where}.{name_field} is required")
            entry_id = _clean_str(entry.get("id"))
            previous = None
            if entry_id:
                if not re.fullmatch(rf"{prefix}-\d+", entry_id):
                    errors.append(f"{where}.id must look like {prefix}-N (got {entry_id!r})")
                previous = current_by_id.get(entry_id)
            else:
                previous = current_by_key.get(_entry_key(section, entry))
                entry_id = previous["id"] if previous and previous.get("id") not in seen_ids else _next_id(counters, prefix)
            if entry_id in seen_ids:
                errors.append(f"Duplicate id {entry_id}")
            seen_ids.add(entry_id)
            entry["id"] = entry_id
            entry["technologies"] = [display(_clean_str(t)) for t in _as_list(entry.get("technologies"), f"{where}.technologies", errors) if _clean_str(t)]

            prev_bullets = {norm_text(b.get("text", "")): b.get("id") for b in (previous or {}).get("bullets") or [] if isinstance(b, dict)}
            bullet_n = _bullet_counter(entry_id, previous, raw)
            bullets = []
            used_bullet_ids: set[str] = set()
            for b_index, bullet in enumerate(_as_list(entry.get("bullets"), f"{where}.bullets", errors)):
                if isinstance(bullet, str):
                    bullet = {"text": bullet}
                if not isinstance(bullet, dict) or not _clean_str(bullet.get("text")):
                    errors.append(f"{where}.bullets[{b_index}] needs non-empty text")
                    continue
                text = _clean_str(bullet["text"])
                bullet_id = _clean_str(bullet.get("id"))
                if bullet_id and not bullet_id.startswith(f"{entry_id}-b"):
                    errors.append(f"{where}.bullets[{b_index}].id {bullet_id!r} must start with {entry_id}-b")
                if not bullet_id:
                    reuse = prev_bullets.get(norm_text(text))
                    if reuse and reuse not in used_bullet_ids:
                        bullet_id = reuse
                    else:
                        bullet_n += 1
                        bullet_id = f"{entry_id}-b{bullet_n}"
                if bullet_id in used_bullet_ids:
                    errors.append(f"Duplicate bullet id {bullet_id}")
                used_bullet_ids.add(bullet_id)
                bullets.append({"id": bullet_id, "text": text})
            entry["bullets"] = bullets
            entries.append(entry)
        prof[section] = entries

    skills = []
    seen_skills: set[str] = set()
    for index, skill in enumerate(_as_list(prof.get("skills"), "skills", errors)):
        if isinstance(skill, str):
            skill = {"name": skill}
        if not isinstance(skill, dict) or not _clean_str(skill.get("name")):
            errors.append(f"skills[{index}] needs a name")
            continue
        key = canon(skill["name"])
        if key in seen_skills:
            warnings.append(f"Duplicate skill {skill['name']!r} ignored")
            continue
        seen_skills.add(key)
        skills.append({"name": display(_clean_str(skill["name"])), "category": _clean_str(skill.get("category")) or "Skills"})
    prof["skills"] = skills

    absent = []
    for name in _as_list(prof.get("skills_absent"), "skills_absent", errors):
        name = _clean_str(name)
        if not name:
            continue
        if canon(name) in seen_skills:
            errors.append(f"{name!r} is listed in both skills and skills_absent")
        absent.append(display(name))
    prof["skills_absent"] = absent

    certs = []
    for index, cert in enumerate(_as_list(prof.get("certifications"), "certifications", errors)):
        if not isinstance(cert, dict) or not _clean_str(cert.get("name")):
            continue
        cert = {k: _clean_str(v) for k, v in cert.items()}
        if not is_valid_date(cert.get("date")):
            errors.append(f"certifications[{index}].date is not a valid date")
        if not cert.get("id"):
            cert["id"] = _next_id(counters, "cert")
        certs.append(cert)
    prof["certifications"] = certs

    prefs = prof.get("preferences") or {}
    work_mode = _clean_str(prefs.get("work_mode")).lower() or None
    if work_mode not in WORK_MODES:
        errors.append("preferences.work_mode must be remote, hybrid, onsite or any")
    prof["preferences"] = {
        "roles": [_clean_str(r) for r in prefs.get("roles") or [] if _clean_str(r)],
        "locations": [_clean_str(r) for r in prefs.get("locations") or [] if _clean_str(r)],
        "work_mode": work_mode,
    }

    avail = prof.get("availability") or {}
    start = _clean_str(avail.get("start_date"))
    if start and not is_valid_date(start):
        errors.append("availability.start_date must be a date")
    prof["availability"] = {"start_date": start, "notes": _clean_str(avail.get("notes"))}

    auths = []
    for index, auth in enumerate(_as_list(prof.get("authorization"), "authorization", errors)):
        if not isinstance(auth, dict) or not _clean_str(auth.get("country")):
            errors.append(f"authorization[{index}] needs a country")
            continue
        clean = {"country": _clean_str(auth["country"]).upper()}
        for field in ("authorized", "requires_sponsorship"):
            value = auth.get(field)
            if value not in (True, False, None):
                errors.append(f"authorization[{index}].{field} must be true, false or null (unknown)")
            clean[field] = value if value in (True, False) else None
        auths.append(clean)
    prof["authorization"] = auths

    known = set(TEMPLATE) | {"_meta"}
    for key in data:
        if key not in known:
            warnings.append(f"Unknown top-level field {key!r} kept as-is")

    if errors:
        raise ResuError("Profile is invalid; nothing was saved.", errors)

    prof["_meta"] = {
        "schema": SCHEMA_VERSION,
        "revision": int(current.get("_meta", {}).get("revision", 0)),
        "updated_at": current.get("_meta", {}).get("updated_at"),
        "id_counters": counters,
    }
    return prof, warnings


# ---------------------------------------------------------------- diff and save

def _fmt(value) -> str:
    if value in (None, "", [], {}):
        return "(empty)"
    return str(value)


def diff(old: dict | None, new: dict) -> list[str]:
    """Human-readable list of changes from old to new."""
    old = old or {}
    lines: list[str] = []

    def compare(path: str, a, b):
        if a != b:
            lines.append(f"~ {path}: {_fmt(a)} -> {_fmt(b)}")

    for key in ("name", "email", "phone", "location"):
        compare(f"contact.{key}", (old.get("contact") or {}).get(key), new["contact"].get(key))
    old_links = (old.get("contact") or {}).get("links") or {}
    for key in sorted(set(old_links) | set(new["contact"]["links"])):
        compare(f"contact.links.{key}", old_links.get(key), new["contact"]["links"].get(key))
    compare("summary", old.get("summary"), new.get("summary"))

    for section in ENTRY_SECTIONS:
        old_entries = {e["id"]: e for e in old.get(section) or []}
        new_entries = {e["id"]: e for e in new.get(section) or []}
        for entry_id, entry in new_entries.items():
            label = entry.get("organization") or entry.get("institution") or entry.get("name")
            before = old_entries.get(entry_id)
            if before is None:
                lines.append(f"+ {section} {entry_id}: {label} ({len(entry['bullets'])} bullets)")
                continue
            for field in sorted((set(entry) | set(before)) - {"bullets", "id"}):
                compare(f"{section}.{entry_id}.{field}", before.get(field), entry.get(field))
            old_b = {b["id"]: b["text"] for b in before.get("bullets") or []}
            new_b = {b["id"]: b["text"] for b in entry["bullets"]}
            for bid, text in new_b.items():
                if bid not in old_b:
                    lines.append(f"+ {bid}: {text}")
                elif old_b[bid] != text:
                    lines.append(f"~ {bid}: {old_b[bid]!r} -> {text!r}")
            for bid in old_b.keys() - new_b.keys():
                lines.append(f"- {bid}: {old_b[bid]}")
        for entry_id in old_entries.keys() - new_entries.keys():
            entry = old_entries[entry_id]
            label = entry.get("organization") or entry.get("institution") or entry.get("name")
            lines.append(f"- {section} {entry_id}: {label}")

    old_skills = {canon(s["name"]): s["name"] for s in old.get("skills") or []}
    new_skills = {canon(s["name"]): s["name"] for s in new["skills"]}
    for key in new_skills.keys() - old_skills.keys():
        lines.append(f"+ skill: {new_skills[key]}")
    for key in old_skills.keys() - new_skills.keys():
        lines.append(f"- skill: {old_skills[key]}")
    compare("skills_absent", sorted(old.get("skills_absent") or []), sorted(new["skills_absent"]))
    compare("certifications", [c.get("name") for c in old.get("certifications") or []], [c.get("name") for c in new["certifications"]])
    for key in ("preferences", "availability", "authorization"):
        compare(key, old.get(key), new.get(key))
    return lines


def _content(prof: dict) -> dict:
    return {k: v for k, v in prof.items() if k != "_meta"}


def save(data: dict) -> tuple[dict, list[str], list[str]]:
    """Validate and store. Returns (profile, change lines, warnings)."""
    current = load(required=False)
    prof, warnings = normalize(data, current)
    changes = diff(current, prof)
    if current and _content(current) == _content(prof):
        return current, [], warnings
    if current:
        store.write_json(store.history_dir() / f"profile-r{current['_meta']['revision']}.json", current)
    prof["_meta"]["revision"] += 1
    prof["_meta"]["updated_at"] = now_iso()
    store.write_json(store.profile_path(), prof)
    return prof, changes, warnings


# ---------------------------------------------------------------- lookups

def sources(prof: dict) -> dict[str, dict]:
    """Every citable source: entries, bullets and the summary, keyed by ID."""
    index: dict[str, dict] = {}
    if prof.get("summary"):
        index["summary"] = {"kind": "summary", "entry": None, "text": prof["summary"], "technologies": []}
    for section in ENTRY_SECTIONS:
        for entry in prof.get(section) or []:
            label = " ".join(
                _clean_str(entry.get(f))
                for f in ("title", "role", "organization", "name", "degree", "field", "institution")
                if entry.get(f)
            )
            index[entry["id"]] = {
                "kind": section,
                "entry": entry["id"],
                "text": label,
                "technologies": entry.get("technologies") or [],
            }
            for bullet in entry.get("bullets") or []:
                index[bullet["id"]] = {
                    "kind": "bullet",
                    "entry": entry["id"],
                    "text": bullet["text"],
                    "technologies": entry.get("technologies") or [],
                }
    for cert in prof.get("certifications") or []:
        index[cert["id"]] = {"kind": "certification", "entry": cert["id"], "text": f"{cert.get('name', '')} {cert.get('issuer', '')}".strip(), "technologies": []}
    return index


def entry_by_id(prof: dict, entry_id: str) -> tuple[str, dict] | None:
    for section in ENTRY_SECTIONS:
        for entry in prof.get(section) or []:
            if entry["id"] == entry_id:
                return section, entry
    return None


def skill_keys(prof: dict) -> set[str]:
    """Canonical keys of skills the profile confirms, including entry technologies."""
    keys = {canon(s["name"]) for s in prof.get("skills") or []}
    for section in ("experience", "projects"):
        for entry in prof.get(section) or []:
            keys.update(canon(t) for t in entry.get("technologies") or [])
    return keys


def graduation_date(prof: dict) -> str | None:
    dates = [e.get("graduation") or e.get("end") for e in prof.get("education") or []]
    dates = [d for d in dates if d and d != "present"]
    return max(dates) if dates else None
