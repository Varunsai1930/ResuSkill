"""Local setup diagnostics; never import facts or change stored candidate data."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from . import __version__, profile, render
from .util import ResuError


def check(pdf_smoke: bool = False) -> dict:
    root = Path(os.environ.get("RESUSKILL_HOME") or Path.home() / ".resuskill").expanduser()
    checks = []

    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})

    add("python", "ok" if sys.version_info >= (3, 9) else "error", sys.version.split()[0] + " (requires 3.9+)")
    add("template", "ok" if render.TEMPLATE_PATH.is_file() else "error",
        "Bundled resume template found." if render.TEMPLATE_PATH.is_file() else "Reinstall the complete skills/resuskill folder; assets are missing.")
    ancestor = root
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    writable = ancestor.is_dir() and os.access(ancestor, os.W_OK | os.X_OK)
    add("storage", "ok" if writable else "error",
        f"{root} (permission estimate; actual writes may be restricted)" if writable else
        f"Cannot use {root}; choose a writable directory with RESUSKILL_HOME.")
    if (root / "profile.json").exists():
        try:
            current = profile.load()
            profile.normalize(current, current)
            add("profile", "ok", "Saved profile is readable; no data changed.")
        except (ResuError, KeyError, TypeError, ValueError, OSError):
            add("profile", "error", "Saved profile is unreadable or invalid. Restore a backup; doctor never repairs or overwrites it.")
    else:
        add("profile", "warning", "No profile yet. Try `demo --json`, then ask the agent to build a profile from your resume and review `profile diff` before saving.")
    browser = render.find_browser()
    add("pdf_browser", "ok" if browser else "warning", browser or
        "Optional: install Chrome/Edge or set RESUSKILL_BROWSER to its executable. HTML export works without it.")
    if pdf_smoke:
        try:
            with tempfile.TemporaryDirectory(prefix="resuskill-doctor-") as temp:
                source = Path(temp) / "smoke.html"
                source.write_text("<!doctype html><title>ResuSkill check</title><p>Fictional PDF smoke test.</p>", encoding="utf-8")
                render.print_pdf(source, Path(temp) / "smoke.pdf")
            add("pdf_smoke", "ok", "Local browser produced a complete PDF using fictional content.")
        except (ResuError, OSError) as exc:
            add("pdf_smoke", "error", str(exc))
    add("web_search", "info", "Job discovery needs the agent's browsing tools. This offline CLI cannot check their availability or verify live listings.")
    return {"version": __version__, "ready": not any(c["status"] == "error" for c in checks), "checks": checks}
