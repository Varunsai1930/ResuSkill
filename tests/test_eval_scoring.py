"""Test the score calculator with synthetic test records, not client evaluation results."""

import importlib.util
import json
from pathlib import Path

from helpers import IsolatedHome, ROOT

spec = importlib.util.spec_from_file_location("eval_score", ROOT / "evals/score.py")
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


class EvalScoringTests(IsolatedHome):
    def setUp(self):
        super().setUp()
        self.path = Path(self._tmp) / "calculator-test.json"
        (self.path.parent / "test-transcript.txt").write_text("Synthetic calculator test data; no model was evaluated.")
        cases = json.loads((ROOT / "evals/cases.json").read_text())
        self.data = {"client": "codex", "client_version": "test", "model": "test", "revision": "test", "reviewer": "test",
                     "cases": [{"id": c["id"], "transcript": "test-transcript.txt", "passed": True, "claims": 1,
                                "unsupported_claims": 0, "sensitive_questions": 1, "ai_sensitive_answers": 0,
                                "checklist_decisions": 1, "checklist_agreements": 1, "skipped_required_steps": 0} for c in cases]}

    def score(self):
        self.path.write_text(json.dumps(self.data))
        return scorer.score(self.path)

    def test_metrics_and_failures(self):
        result = self.score()
        self.assertEqual(result["cases"], 25)
        self.assertEqual(result["failures"], [])
        self.data["cases"][0]["unsupported_claims"] = 1
        result = self.score()
        self.assertEqual(result["failures"], ["e01"])
        self.assertEqual(result["unsupported_claim_rate"], 1 / 25)

    def test_missing_cases_and_transcripts_cannot_pass(self):
        row = self.data["cases"].pop()
        with self.assertRaises(ValueError):
            self.score()
        self.data["cases"].append(row)
        row["transcript"] = "missing.txt"
        with self.assertRaises(ValueError):
            self.score()

    def test_zero_denominators_do_not_look_like_zero_failures(self):
        for row in self.data["cases"]:
            row["claims"] = 0
        with self.assertRaises(ValueError):
            self.score()

    def test_invalid_counts_cannot_pass(self):
        for count in (True, -1, 0.5):
            self.data["cases"][0]["claims"] = count
            with self.assertRaises(ValueError):
                self.score()
