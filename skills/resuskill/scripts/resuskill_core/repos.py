"""Rank the user's public GitHub repositories against a saved job.

Offline: the agent fetches the repository list (GitHub's public API output) and passes it in.
Repository text is untrusted data. Nothing here is stored or added to the profile; a repository
reaches a resume only after the user confirms it as a profile project.
"""

from __future__ import annotations

import re

from . import jobs as jobs_mod
from . import profile as profile_mod
from .skills import canon, display, find_terms
from .util import ResuError

README_LIMIT = 20000  # characters of README scanned per repository
REQUIRED_WEIGHT, OTHER_WEIGHT = 4, 2
README_ONLY_WEIGHT = 1  # a README can name a technology without using it (examples, comparisons)


def _norm_link(url) -> str:
    text = str(url or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^www\.", "", text)
    return re.sub(r"(\.git)?/*$", "", text)


def _job_terms(job: dict) -> dict[str, int]:
    """Canonical job technology -> weight. Required skill criteria weigh more than other mentions."""
    weights: dict[str, int] = {key: OTHER_WEIGHT for key in find_terms(job["description"])}
    for req in job["requirements"]:
        crit = req.get("criterion") or {}
        if crit.get("type") != "skill":
            continue
        weight = REQUIRED_WEIGHT if req["importance"] == "required" else OTHER_WEIGHT
        for skill in crit["skills"]:
            key = canon(skill)
            weights[key] = max(weights.get(key, 0), weight)
    return weights


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _check(repos) -> list[dict]:
    if not isinstance(repos, list):
        raise ResuError("Repository input must be a JSON list (GitHub's /users/<name>/repos output)")
    errors = []
    for i, repo in enumerate(repos):
        if not isinstance(repo, dict):
            errors.append(f"[{i}] must be an object")
            continue
        for field in ("name", "html_url"):
            if not _text(repo.get(field)).strip():
                errors.append(f"[{i}].{field} must be non-empty text")
        for field in ("description", "language", "readme", "pushed_at"):
            if repo.get(field) is not None and not isinstance(repo[field], str):
                errors.append(f"[{i}].{field} must be text or null")
        if repo.get("topics") is not None and not (isinstance(repo["topics"], list) and all(isinstance(t, str) for t in repo["topics"])):
            errors.append(f"[{i}].topics must be a list of text")
        languages = repo.get("languages")
        if languages is not None:
            if isinstance(languages, list):
                if not all(isinstance(name, str) and name.strip() for name in languages):
                    errors.append(f"[{i}].languages must contain non-empty language names")
            elif isinstance(languages, dict):
                if not all(isinstance(name, str) and name.strip() and type(count) is int and count >= 0
                           for name, count in languages.items()):
                    errors.append(f"[{i}].languages must map non-empty names to non-negative integer byte counts")
            else:
                errors.append(f"[{i}].languages must be a list or an object")
        for field in ("fork", "archived"):
            if field in repo and type(repo[field]) is not bool:
                errors.append(f"[{i}].{field} must be a boolean")
        for field in ("size", "stargazers_count"):
            if field in repo and (type(repo[field]) is not int or repo[field] < 0):
                errors.append(f"[{i}].{field} must be a non-negative integer")
    if errors:
        raise ResuError("Invalid repository input; nothing was ranked", errors)
    return repos


def rank(job_id: str, repos) -> dict:
    job = jobs_mod.load(job_id)
    prof = profile_mod.load()
    repos = _check(repos)
    weights = _job_terms(job)
    in_profile = {_norm_link(p.get("link")): p["id"] for p in prof.get("projects") or [] if p.get("link")}
    candidates, excluded = [], []
    for repo in repos:
        name, url = repo["name"].strip(), repo["html_url"].strip()
        if repo.get("fork") is True:
            excluded.append({"name": name, "url": url, "reason": "fork of someone else's repository"})
            continue
        if repo.get("size") == 0:
            excluded.append({"name": name, "url": url, "reason": "empty repository"})
            continue
        languages = repo.get("languages") or []
        language_names = list(languages) if isinstance(languages, dict) else languages
        extra = tuple(display(name) for name in language_names) + tuple(display(key) for key in weights)
        if repo.get("language"):
            extra += (display(repo["language"]),)
        metadata = " ".join([name.replace("-", " ").replace("_", " "), _text(repo.get("description")),
                             " ".join(repo.get("topics") or []), _text(repo.get("language")), " ".join(language_names)])
        found = find_terms(metadata, extra)
        # Topics are structured, lowercase tags: prose capitalization rules do not apply.
        found |= {canon(topic) for topic in repo.get("topics") or [] if canon(topic) in weights}
        readme_only = find_terms(_text(repo.get("readme"))[:README_LIMIT], extra) - found
        matched = sorted((k for k in found if k in weights), key=lambda k: (-weights[k], k))
        matched_readme = sorted((k for k in readme_only if k in weights), key=lambda k: (-weights[k], k))
        notes = []
        if repo.get("archived") is True:
            notes.append("archived")
        if not _text(repo.get("readme")).strip() and not _text(repo.get("description")).strip():
            notes.append("no README or description: ask the user what it does")
        candidates.append({
            "name": name,
            "url": url,
            "score": sum(weights[k] for k in matched) + README_ONLY_WEIGHT * len(matched_readme),
            "matches_job": [display(k) for k in matched],
            "readme_mentions_job": [display(k) for k in matched_readme],
            "other_technologies": sorted(display(k) for k in found - set(matched)),
            "other_readme_mentions": sorted(display(k) for k in readme_only - set(matched_readme)),
            "in_profile": in_profile.get(_norm_link(url)),
            "pushed_at": _text(repo.get("pushed_at")) or None,
            "stars": repo.get("stargazers_count") if isinstance(repo.get("stargazers_count"), int) else None,
            "description": _text(repo.get("description")).strip(),
            "notes": notes,
        })
    # Highest score first; among equal scores, most recently pushed first (stable two-pass sort).
    candidates.sort(key=lambda c: c["pushed_at"] or "", reverse=True)
    candidates.sort(key=lambda c: c["score"], reverse=True)
    warnings = []
    if not job["requirements"]:
        warnings.append("No requirements saved for this job; ranking uses technologies named in the description only")
    if not any(_text(r.get("readme")).strip() for r in repos if isinstance(r, dict)):
        warnings.append("No READMEs supplied; ranking uses names, descriptions, topics and languages only")
    return {"job": job_id, "candidates": candidates, "excluded": excluded, "warnings": warnings}
