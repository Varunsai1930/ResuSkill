"""The application package: resume proposals vs accepted resume, questions, answers, approval.

Review state is Draft, Approved or Stale. Editing content clears approval; a changed
profile or job revision makes an approved package Stale. Approval never means Applied.
"""

from __future__ import annotations

from . import jobs as jobs_mod
from . import profile as profile_mod
from . import questions as q_mod
from . import store, validate
from .util import ResuError, content_hash, now_iso

DRAFT, APPROVED, STALE = "draft", "approved", "stale"


def _path(job_id: str):
    return store.job_dir(job_id) / "package.json"


def load(job_id: str) -> dict:
    return store.read_json(_path(job_id), default=None) or {
        "resume": None,
        "resume_accepted_at": None,
        "answers": {},
        "answer_proposals": {},
        "approval": None,
    }


def save(job_id: str, pkg: dict, content_changed: bool = True) -> None:
    if content_changed:
        pkg["approval"] = None
    pkg["updated_at"] = now_iso()
    store.write_json(_path(job_id), pkg)


def load_proposal(job_id: str) -> dict | None:
    return store.read_json(store.job_dir(job_id) / "proposal.json")


def review_state(job: dict, pkg: dict, prof: dict | None) -> str:
    approval = pkg.get("approval")
    if not approval:
        return DRAFT
    if not prof or approval["profile_revision"] != prof["_meta"]["revision"] or approval["job_revision"] != job["revision"]:
        return STALE
    return APPROVED


# ---------------------------------------------------------------- resume

def propose_resume(job_id: str, data, model: str = "") -> tuple[dict, list[str]]:
    job = jobs_mod.load(job_id)
    prof = profile_mod.load()
    clean, warnings = validate.validate_proposal(prof, job, data)
    record = {
        "proposal": clean,
        "warnings": warnings,
        "created_at": now_iso(),
        "profile_revision": prof["_meta"]["revision"],
        "job_revision": job["revision"],
        "model": model,
    }
    store.write_json(store.job_dir(job_id) / "proposal.json", record)
    return record, warnings


def accept_resume(job_id: str) -> dict:
    record = load_proposal(job_id)
    if not record:
        raise ResuError("No resume proposal to accept. Run `resume propose` first.")
    job = jobs_mod.load(job_id)
    prof = profile_mod.load()
    clean, _ = validate.validate_proposal(prof, job, record["proposal"])
    pkg = load(job_id)
    pkg["resume"] = clean
    pkg["resume_accepted_at"] = now_iso()
    pkg["resume_profile_revision"] = prof["_meta"]["revision"]
    save(job_id, pkg)
    return pkg


# ---------------------------------------------------------------- questions

def _question(job: dict, qid: str) -> dict:
    for question in job.get("questions") or []:
        if question["id"] == qid:
            return question
    raise ResuError(f"Job {job['id']} has no question {qid!r}")


def add_question(job_id: str, text: str, required: bool, limit: int | None, unit: str, category: str | None) -> dict:
    text = text.strip()
    if not text:
        raise ResuError("Question text is required")
    if unit not in ("chars", "words"):
        raise ResuError("Limit unit must be chars or words")
    job = jobs_mod.load(job_id)
    detected, key = q_mod.classify(text)
    if category and category != detected:
        if category not in q_mod.CATEGORIES:
            raise ResuError(f"Category must be one of {', '.join(q_mod.CATEGORIES)}")
        if category == q_mod.FACTUAL and not key:
            raise ResuError("No profile field matches this question; use open or sensitive instead")
        detected = category
    existing = [int(q["id"][1:]) for q in job.get("questions") or [] if q["id"][1:].isdigit()]
    question = {
        "id": f"q{max(existing, default=0) + 1}",
        "text": text,
        "required": required,
        "limit": limit,
        "limit_unit": unit,
        "category": detected,
        "factual_key": key if detected in (q_mod.FACTUAL, q_mod.SENSITIVE_FACTUAL) else None,
        "added_at": now_iso(),
    }
    job.setdefault("questions", []).append(question)
    jobs_mod.save(job)
    save(job_id, load(job_id))  # a new question clears approval
    return question


def set_category(job_id: str, qid: str, category: str) -> dict:
    if category not in q_mod.CATEGORIES or category == q_mod.UNKNOWN:
        raise ResuError("Category must be factual, sensitive_factual, sensitive or open")
    job = jobs_mod.load(job_id)
    question = _question(job, qid)
    _, key = q_mod.classify(question["text"])
    if category in (q_mod.FACTUAL, q_mod.SENSITIVE_FACTUAL) and not key:
        raise ResuError("No profile field matches this question; use open or sensitive instead")
    question["category"] = category
    question["factual_key"] = key if category in (q_mod.FACTUAL, q_mod.SENSITIVE_FACTUAL) else None
    jobs_mod.save(job)
    pkg = load(job_id)
    pkg["answers"].pop(qid, None)
    pkg["answer_proposals"].pop(qid, None)
    save(job_id, pkg)
    return question


def remove_question(job_id: str, qid: str) -> None:
    job = jobs_mod.load(job_id)
    _question(job, qid)
    job["questions"] = [q for q in job["questions"] if q["id"] != qid]
    jobs_mod.save(job)
    pkg = load(job_id)
    pkg["answers"].pop(qid, None)
    pkg["answer_proposals"].pop(qid, None)
    save(job_id, pkg)


# ---------------------------------------------------------------- answers

def propose_answers(job_id: str, drafts, model: str = "") -> list[str]:
    """Store AI drafts for open questions. All-or-nothing."""
    if isinstance(drafts, dict) and "answers" in drafts:
        drafts = drafts["answers"]
    if not isinstance(drafts, list):
        raise ResuError("Answer drafts must be a list of {question_id, text, sources}")
    job = jobs_mod.load(job_id)
    prof = profile_mod.load()
    pkg = load(job_id)
    errors: list[str] = []
    staged = {}
    for index, draft in enumerate(drafts):
        qid = str((draft or {}).get("question_id", ""))
        try:
            question = _question(job, qid)
        except ResuError as exc:
            errors.append(f"answers[{index}]: {exc}")
            continue
        if question["category"] != q_mod.OPEN:
            errors.append(f"{qid}: only open questions get AI drafts (this one is {question['category']})")
            continue
        text = str(draft.get("text", "")).strip()
        cited = [str(s) for s in draft.get("sources") or []]
        for problem in validate.validate_answer(prof, job, text, cited, question.get("limit"), question.get("limit_unit", "chars")):
            errors.append(f"{qid}: {problem}")
        staged[qid] = {"text": text, "sources": cited, "bank_id": draft.get("bank_id"), "created_at": now_iso(), "model": model}
    if errors:
        raise ResuError("Answer drafts rejected; nothing was stored.", errors)
    pkg["answer_proposals"].update(staged)
    save(job_id, pkg, content_changed=False)
    return sorted(staged)


def accept_answers(job_id: str, qids: list[str]) -> list[str]:
    job = jobs_mod.load(job_id)
    prof = profile_mod.load()
    pkg = load(job_id)
    targets = qids or sorted(pkg["answer_proposals"])
    if not targets:
        raise ResuError("No pending answer drafts to accept")
    for qid in targets:
        question = _question(job, qid)
        draft = pkg["answer_proposals"].get(qid)
        if not draft:
            raise ResuError(f"{qid} has no pending draft")
        problems = validate.validate_answer(prof, job, draft["text"], draft["sources"], question.get("limit"), question.get("limit_unit", "chars"))
        if problems:
            raise ResuError(f"{qid} no longer validates against the profile", problems)
    for qid in targets:
        draft = pkg["answer_proposals"].pop(qid)
        pkg["answers"][qid] = {"text": draft["text"], "sources": draft["sources"], "source": "ai_draft", "at": now_iso()}
    save(job_id, pkg)
    return targets


def set_answer(job_id: str, qid: str, text: str | None, skip: bool = False) -> dict:
    """Store the user's own answer (or an explicit skip for an optional question)."""
    job = jobs_mod.load(job_id)
    question = _question(job, qid)
    pkg = load(job_id)
    if skip:
        if question["required"]:
            raise ResuError(f"{qid} is required and cannot be skipped")
        answer = {"text": "", "source": "user", "skipped": True, "at": now_iso()}
    else:
        text = (text or "").strip()
        if not text:
            raise ResuError("Answer text is empty; use --skip for optional questions")
        problem = validate.check_length(text, question.get("limit"), question.get("limit_unit", "chars"))
        if problem:
            raise ResuError(f"{qid}: {problem}")
        answer = {"text": text, "source": "user", "at": now_iso()}
    pkg["answers"][qid] = answer
    pkg["answer_proposals"].pop(qid, None)
    save(job_id, pkg)
    return answer


def confirm_answer(job_id: str, qid: str) -> dict:
    """User confirms the profile value for a factual or sensitive-factual question."""
    job = jobs_mod.load(job_id)
    question = _question(job, qid)
    if question["category"] not in (q_mod.FACTUAL, q_mod.SENSITIVE_FACTUAL):
        raise ResuError(f"{qid} is {question['category']}; only profile-backed answers can be confirmed")
    prof = profile_mod.load()
    value = q_mod.factual_value(question["factual_key"], question["text"], prof)
    if value is None:
        raise ResuError(f"The profile has no value for {question['factual_key']}; update the profile or use `answers set`")
    pkg = load(job_id)
    pkg["answers"][qid] = {"text": value, "source": "profile", "confirmed": True, "key": question["factual_key"], "at": now_iso()}
    save(job_id, pkg)
    return pkg["answers"][qid]


def bank_save(job_id: str, qid: str) -> dict:
    job = jobs_mod.load(job_id)
    question = _question(job, qid)
    answer = load(job_id)["answers"].get(qid)
    if not answer or answer.get("skipped"):
        raise ResuError(f"{qid} has no accepted answer to save")
    if question["category"] in (q_mod.SENSITIVE, q_mod.SENSITIVE_FACTUAL):
        raise ResuError("Sensitive answers are never stored in the answer bank")
    return q_mod.bank_save(question["text"], answer["text"], f"{job_id}/{qid}")


# ---------------------------------------------------------------- resolution and approval

LABELS = {
    "profile": "From profile",
    "ai_draft": "AI draft",
    "user": "User answer",
    "missing": "Missing information",
    "input": "User input required",
    "pending": "AI draft (pending review)",
    "skipped": "Skipped (optional)",
    "category": "Confirm category",
}


def resolve_answer(question: dict, answer: dict | None, proposal: dict | None, prof: dict) -> dict:
    """Current text, label and whether it is resolved for approval."""
    category = question["category"]
    if answer and answer.get("skipped"):
        return {"text": "", "label": LABELS["skipped"], "resolved": True}
    if category == q_mod.UNKNOWN:
        return {"text": "", "label": LABELS["category"], "resolved": False}
    if category in (q_mod.FACTUAL, q_mod.SENSITIVE_FACTUAL):
        value = q_mod.factual_value(question["factual_key"], question["text"], prof)
        if answer and answer.get("source") == "user":
            return {"text": answer["text"], "label": LABELS["user"], "resolved": True}
        if category == q_mod.SENSITIVE_FACTUAL:
            if answer and answer.get("confirmed") and answer["text"] == value:
                return {"text": value, "label": LABELS["profile"] + " (confirmed)", "resolved": True}
            return {"text": value or "", "label": LABELS["input"], "resolved": False}
        if value is None:
            return {"text": "", "label": LABELS["missing"], "resolved": False}
        return {"text": value, "label": LABELS["profile"], "resolved": True}
    if answer:
        return {"text": answer["text"], "label": LABELS[answer["source"]], "resolved": True}
    if category == q_mod.SENSITIVE:
        return {"text": "", "label": LABELS["input"], "resolved": False}
    if proposal:
        return {"text": proposal["text"], "label": LABELS["pending"], "resolved": False}
    return {"text": "", "label": LABELS["missing"], "resolved": False}


def resolved(job: dict, prof: dict, pkg: dict) -> dict:
    answers = []
    for question in job.get("questions") or []:
        result = resolve_answer(question, pkg["answers"].get(question["id"]), pkg["answer_proposals"].get(question["id"]), prof)
        answers.append({"id": question["id"], "question": question["text"], "required": question["required"], "category": question["category"], **result})
    return {"resume": pkg.get("resume"), "answers": answers}


def check(job_id: str) -> tuple[list[str], list[str]]:
    """Blockers and warnings for approval."""
    job = jobs_mod.load(job_id)
    prof = profile_mod.load()
    pkg = load(job_id)
    blockers: list[str] = []
    warnings: list[str] = []
    if not pkg.get("resume"):
        blockers.append("No accepted resume. Propose one and run `resume accept`.")
    else:
        try:
            validate.validate_proposal(prof, job, pkg["resume"])
        except ResuError as exc:
            blockers.append("Accepted resume no longer validates against the profile: " + "; ".join(exc.details[:5]))
    for item in resolved(job, prof, pkg)["answers"]:
        if item["resolved"]:
            continue
        question = _question(job, item["id"])
        if question["category"] in (q_mod.SENSITIVE, q_mod.SENSITIVE_FACTUAL):
            blockers.append(f"{item['id']} ({item['label']}): sensitive answers need the user's own answer, confirmation or an explicit skip")
        elif question["category"] == q_mod.UNKNOWN:
            blockers.append(f"{item['id']}: confirm the question category with `questions categorize`")
        elif question["required"]:
            blockers.append(f"{item['id']} ({item['label']}): required question has no accepted answer")
        else:
            warnings.append(f"{item['id']} ({item['label']}): optional question unanswered")
    proposal = load_proposal(job_id)
    if proposal and pkg.get("resume_accepted_at") and proposal["created_at"] > pkg["resume_accepted_at"]:
        warnings.append("A newer resume proposal exists that has not been accepted")
    if pkg.get("answer_proposals"):
        warnings.append(f"Pending answer drafts not accepted: {', '.join(sorted(pkg['answer_proposals']))}")
    if not job.get("requirements"):
        warnings.append("No requirements were reviewed for this job")
    return blockers, warnings


def approve(job_id: str) -> dict:
    blockers, warnings = check(job_id)
    if blockers:
        raise ResuError("Package cannot be approved yet.", blockers)
    job = jobs_mod.load(job_id)
    prof = profile_mod.load()
    pkg = load(job_id)
    package_view = resolved(job, prof, pkg)
    pkg["approval"] = {
        "hash": content_hash(package_view),
        "at": now_iso(),
        "profile_revision": prof["_meta"]["revision"],
        "job_revision": job["revision"],
        "warnings": warnings,
    }
    save(job_id, pkg, content_changed=False)
    return pkg
