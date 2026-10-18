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
    """Comparable repository link: "github.com/owner/repo/tree/main#readme" -> "github.com/owner/repo"."""
    text = str(url or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^www\.", "", text)
    text = re.split(r"[?#]", text, maxsplit=1)[0]
    parts = [p for p in text.split("/") if p]
    if parts[:1] == ["github.com"] and len(parts) >= 3:
        parts = parts[:3]
    return re.sub(r"\.git$", "", "/".join(parts))


def _one_line(value, limit: int = 300) -> str:
    """Untrusted repository text as one plain line, so it cannot imitate CLI output lines."""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+", " ", _text(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "\u2026"


def _readme_failed(text: str) -> bool:
    """A GitHub API error body (rate limit, not found) passed in place of README text."""
    head = text.lstrip()[:400]
    return head.startswith("{") and '"message"' in head and ("documentation_url" in head or "rate limit" in head.lower())


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
    # One extra-term set for the whole run: find_terms compiles and caches a pattern set per distinct set.
    all_languages = set()
    for repo in repos:
        languages = repo.get("languages") or []
        all_languages.update(languages)
        if repo.get("language"):
            all_languages.add(repo["language"])
    extra = tuple(sorted({display(n) for n in all_languages} | {display(k) for k in weights} | {"Jupyter"}))
    # Display names as written ("Jupyter Notebook"), not the lowercase comparison keys.
    shown = {canon(t): t for t in extra}

    def label(key: str) -> str:
        return shown.get(key) or display(key)
    candidates, excluded = [], []
    failed_readmes = 0
    for repo in repos:
        name, url = _one_line(repo["name"], 100), repo["html_url"].strip()
        if repo.get("size") == 0:
            excluded.append({"name": name, "url": url, "reason": "empty repository"})
            continue
        languages = repo.get("languages") or []
        language_names = list(languages) if isinstance(languages, dict) else languages
        readme = _text(repo.get("readme"))
        if readme and _readme_failed(readme):
            readme = ""
            failed_readmes += 1
        metadata = " ".join([name.replace("-", " ").replace("_", " "), _text(repo.get("description")),
                             " ".join(repo.get("topics") or []), _text(repo.get("language")), " ".join(language_names)])
        found = find_terms(metadata, extra)
        # Topics are structured, lowercase tags: prose capitalization rules do not apply.
        found |= {canon(topic) for topic in repo.get("topics") or [] if canon(topic) in weights}
        readme_only = find_terms(readme[:README_LIMIT], extra) - found
        matched = sorted((k for k in found if k in weights), key=lambda k: (-weights[k], k))
        matched_readme = sorted((k for k in readme_only if k in weights), key=lambda k: (-weights[k], k))
        notes = []
        if repo.get("fork") is True:
            notes.append("fork: suggest it only if the user says it contains substantial work of their own")
        if repo.get("archived") is True:
            notes.append("archived")
        if canon("Jupyter") in found:
            notes.append("notebook repository: check the notebooks' kernel language before listing it")
        if _text(repo.get("readme")) and not readme:
            notes.append("README fetch returned a GitHub error, not README text")
        if not readme.strip() and not _text(repo.get("description")).strip():
            notes.append("no README or description: ask the user what it does")
        candidates.append({
            "name": name,
            "url": url,
            "score": sum(weights[k] for k in matched) + README_ONLY_WEIGHT * len(matched_readme),
            "matches_job": [label(k) for k in matched],
            "readme_mentions_job": [label(k) for k in matched_readme],
            "other_technologies": sorted(label(k) for k in found - set(matched)),
            "other_readme_mentions": sorted(label(k) for k in readme_only - set(matched_readme)),
            "in_profile": in_profile.get(_norm_link(url)),
            "pushed_at": _text(repo.get("pushed_at")) or None,
            "stars": repo.get("stargazers_count") if isinstance(repo.get("stargazers_count"), int) else None,
            "description": _one_line(repo.get("description")),
            "notes": notes,
        })
    # Highest score first; among equal scores, most recently pushed first; forks after own repositories.
    candidates.sort(key=lambda c: c["pushed_at"] or "", reverse=True)
    candidates.sort(key=lambda c: c["score"], reverse=True)
    candidates.sort(key=lambda c: any(n.startswith("fork:") for n in c["notes"]))
    warnings = []
    if not job["requirements"]:
        warnings.append("No requirements saved for this job; ranking uses technologies named in the description only")
    if failed_readmes:
        warnings.append(f"{failed_readmes} README(s) were GitHub error responses (often the 60-requests-per-hour "
                        "limit) and were ignored; ranking for those repositories uses metadata only")
    elif not any(_text(r.get("readme")).strip() for r in repos):
        warnings.append("No READMEs supplied; ranking uses names, descriptions, topics and languages only")
    return {"job": job_id, "candidates": candidates, "excluded": excluded, "warnings": warnings}
