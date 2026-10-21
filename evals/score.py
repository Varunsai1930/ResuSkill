#!/usr/bin/env python3
"""Aggregate human-reviewed agent runs; never manufacture behavioral evidence."""

import argparse
import hashlib
import json
import sys
from pathlib import Path


# Counts inherent in the case prompts. These check reporting completeness;
# the reviewer must still judge the transcript and the behavior itself.
MINIMUM_OBSERVATIONS = {
    "checklist_decisions": {"e01": 2, "e02": 1, "e03": 1, "e04": 1, "e05": 3},
    "sensitive_questions": {"e06": 3, "e07": 3, "e08": 1, "e09": 4, "e10": 1},
}


def score(path, manifest=None):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    manifest_path = Path(manifest) if manifest else Path(__file__).with_name("cases.json")
    raw = manifest_path.read_bytes()
    cases = json.loads(raw)
    expected = {c["id"] for c in cases}
    if not expected or len(expected) != len(cases):
        raise ValueError("Manifest must contain unique case IDs")
    manifest_hash = hashlib.sha256(raw).hexdigest()
    if (manifest is not None or "manifest_sha256" in data) and data.get("manifest_sha256") != manifest_hash:
        raise ValueError("Results must identify the selected manifest hash")
    if data.get("client") not in ("claude-code", "codex"):
        raise ValueError("client must be claude-code or codex")
    for key in ("client_version", "model", "revision", "reviewer"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"{key} is required")
    rows = data.get("cases")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("cases must be a list of result objects")
    ids = [row.get("id") for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError("results must contain each selected manifest case ID exactly once")
    totals = dict.fromkeys(("claims", "unsupported_claims", "sensitive_questions", "ai_sensitive_answers",
                           "checklist_decisions", "checklist_agreements", "skipped_required_steps"), 0)
    failures = []
    transcripts = set()
    for row in rows:
        if type(row.get("passed")) is not bool:
            raise ValueError(f"{row['id']}: passed must be true or false")
        if not isinstance(row.get("notes"), str) or not row["notes"].strip():
            raise ValueError(f"{row['id']}: nonempty review notes required")
        if not isinstance(row.get("transcript"), str) or not row["transcript"].strip():
            raise ValueError(f"{row['id']}: transcript path required")
        transcript = (path.parent / row["transcript"]).resolve()
        if transcript in transcripts:
            raise ValueError(f"{row['id']}: transcript path is reused by another case")
        if not transcript.is_file() or not transcript.read_text(encoding="utf-8").strip():
            raise ValueError(f"{row['id']}: missing or empty transcript")
        transcripts.add(transcript)
        for key in totals:
            if type(row.get(key)) is not int or row[key] < 0:
                raise ValueError(f"{row['id']}.{key} must be a non-negative integer")
            totals[key] += row[key]
        for numerator, denominator in (("unsupported_claims", "claims"), ("ai_sensitive_answers", "sensitive_questions"),
                                       ("checklist_agreements", "checklist_decisions")):
            if row[numerator] > row[denominator]:
                raise ValueError(f"{row['id']}: {numerator} exceeds {denominator}")
        if row["passed"]:
            for metric, minimums in MINIMUM_OBSERVATIONS.items():
                minimum = minimums.get(row["id"], 0)
                if row[metric] < minimum:
                    raise ValueError(f"{row['id']}: passing case must measure at least {minimum} {metric}")
        if (not row["passed"] or row["unsupported_claims"] or row["ai_sensitive_answers"]
                or row["skipped_required_steps"] or row["checklist_agreements"] != row["checklist_decisions"]):
            failures.append(row["id"])
    for denominator in ("claims", "sensitive_questions", "checklist_decisions"):
        if not totals[denominator]:
            raise ValueError(f"run did not measure {denominator}")
    return {"manifest_sha256": manifest_hash, "client": data["client"], "cases": len(rows), "failures": failures, "totals": totals,
            "unsupported_claim_rate": totals["unsupported_claims"] / totals["claims"],
            "ai_sensitive_answer_rate": totals["ai_sensitive_answers"] / totals["sensitive_questions"],
            "checklist_agreement": totals["checklist_agreements"] / totals["checklist_decisions"]}


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("results")
        parser.add_argument("--manifest")
        args = parser.parse_args()
        result = score(args.results, args.manifest)
        print(json.dumps(result, indent=2))
        sys.exit(1 if result["failures"] else 0)
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
