"""Filesystem storage. All data lives under RESUSKILL_HOME (default ~/.resuskill)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .util import ResuError


_UNSET = object()


def check_version(data, name: str, version=_UNSET) -> None:
    from . import SCHEMA_VERSION

    if not isinstance(data, dict):
        raise ResuError(f"Stored {name} must be a JSON object; restore a valid backup")
    value = data.get("schema_version", SCHEMA_VERSION) if version is _UNSET else version
    if type(value) is not int or value != SCHEMA_VERSION:
        raise ResuError(f"Unsupported {name} schema version {value!r}. Update ResuSkill or restore a compatible backup; data was not changed.")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ResuError(f"Duplicate JSON key {key!r}; keep exactly one value")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ResuError(f"Invalid JSON number {value}; use a finite number or null")


def home() -> Path:
    root = os.environ.get("RESUSKILL_HOME")
    path = Path(root).expanduser() if root else Path.home() / ".resuskill"
    path.mkdir(parents=True, exist_ok=True)
    return path


def profile_path() -> Path:
    return home() / "profile.json"


def history_dir() -> Path:
    path = home() / "history"
    path.mkdir(exist_ok=True)
    return path


def jobs_dir() -> Path:
    path = home() / "jobs"
    path.mkdir(exist_ok=True)
    return path


def job_dir(job_id: str) -> Path:
    if not job_id or "/" in job_id or "\\" in job_id or job_id.startswith("."):
        raise ResuError(f"Invalid job id: {job_id!r}")
    path = jobs_dir() / job_id
    if not path.is_dir():
        raise ResuError(f"No job with id {job_id!r}. Run `jobs` to list saved jobs.")
    return path


def bank_path() -> Path:
    return home() / "answer_bank.json"


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise ResuError(f"Stored file is not valid JSON: {path} ({exc})") from exc


def write_json(path: Path, data) -> None:
    """Atomic write so an interrupted command never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, allow_nan=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _read_stdin() -> str:
    """Stdin as UTF-8 regardless of locale (Windows pipes default to a legacy code page)."""
    import sys

    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is None:
        return sys.stdin.read()
    try:
        return buffer.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ResuError(f"Input on stdin is not UTF-8 text: {exc}") from exc


def load_input(path_arg: str):
    """Load agent-supplied JSON from a file path, or from stdin when the path is '-'."""
    try:
        if path_arg == "-":
            return json.loads(_read_stdin(), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        with open(Path(path_arg).expanduser(), encoding="utf-8-sig") as fh:
            return json.load(fh, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except FileNotFoundError as exc:
        raise ResuError(f"Input file not found: {path_arg}") from exc
    except json.JSONDecodeError as exc:
        raise ResuError(f"Input is not valid JSON: {exc}") from exc


def load_text(path_arg: str) -> str:
    if path_arg == "-":
        return _read_stdin()
    try:
        return Path(path_arg).expanduser().read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ResuError(f"Input file not found: {path_arg}") from exc
