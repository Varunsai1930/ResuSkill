"""Shared helpers: errors, time, text normalization, partial dates, JSON hashing."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone


class ResuError(Exception):
    """A user-facing error. The CLI prints the message and exits non-zero."""

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stamp() -> str:
    """Filesystem-safe UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


_QUOTES = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "−": "-", " ": " ", "•": " ", "·": " ",
}


def norm_text(text: str) -> str:
    """Casefold, unify quotes/dashes and collapse whitespace for substring checks."""
    text = unicodedata.normalize("NFKC", text or "")
    text = "".join(_QUOTES.get(ch, ch) for ch in text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def slugify(text: str, max_len: int = 40) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:max_len].strip("-") or "item"


# Partial dates are stored as "YYYY", "YYYY-MM" or "YYYY-MM-DD"; "present" marks ongoing.
_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")


def is_valid_date(value) -> bool:
    if value in (None, ""):
        return True
    if value == "present":
        return True
    match = _DATE_RE.match(str(value))
    if not match:
        return False
    month = match.group(2)
    return month is None or 1 <= int(month) <= 12


def date_key(value, end_of_period: bool = False) -> tuple[int, int, int] | None:
    """Comparable tuple for a partial date. Missing parts fill to the start or end of the period."""
    if value in (None, ""):
        return None
    if value == "present":
        today = datetime.now(timezone.utc)
        return (today.year, today.month, today.day)
    match = _DATE_RE.match(str(value))
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else (12 if end_of_period else 1)
    day = int(match.group(3)) if match.group(3) else (31 if end_of_period else 1)
    return (year, month, day)


def today_key() -> tuple[int, int, int]:
    today = datetime.now(timezone.utc)
    return (today.year, today.month, today.day)


def canonical_json(data) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def content_hash(data) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()[:16]
