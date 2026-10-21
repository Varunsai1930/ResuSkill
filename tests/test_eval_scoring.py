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
        cases = json.loads((ROOT / "evals/cases.json").read_text())
        decisions = {"e01": 2, "e02": 1, "e03": 1, "e04": 1, "e05": 3}
        questions = {"e06": 3, "e07": 3, "e08": 1, "e09": 4, "e10": 1}
        rows = []
        for case in cases:
            case_id = case["id"]
            transcript = f"{case_id}-calculator-transcript.txt"
            (self.path.parent / transcript).write_text(
                f"Synthetic calculator test data for {case_id}; no model was evaluated.")
            rows.append({"id": case_id, "transcript": transcript, "passed": True,
                         "claims": int(case_id in ("e11", "e12", "e14", "e16")),
                         "unsupported_claims": 0, "sensitive_questions": questions.get(case_id, 0),
                         "ai_sensitive_answers": 0, "checklist_decisions": decisions.get(case_id, 0),
                         "checklist_agreements": decisions.get(case_id, 0), "skipped_required_steps": 0,
                         "notes": f"Synthetic review record for calculator case {case_id}; no behavioral evidence."})
        self.data = {"client": "codex", "client_version": "test", "model": "test", "revision": "test", "reviewer": "test",
                     "cases": rows}

    def score(self):
        self.path.write_text(json.dumps(self.data))
        return scorer.score(self.path)

    def test_metrics_and_failures(self):
        result = self.score()
        self.assertEqual(result["cases"], 25)
        self.assertEqual(result["failures"], [])
        self.data["cases"][10]["unsupported_claims"] = 1
        result = self.score()
        self.assertEqual(result["failures"], ["e11"])
        self.assertEqual(result["unsupported_claim_rate"], 1 / 4)
        self.assertEqual(result["totals"]["sensitive_questions"], 12)
        self.assertEqual(result["totals"]["checklist_decisions"], 8)

    def test_missing_cases_and_transcripts_cannot_pass(self):
        row = self.data["cases"].pop()
        with self.assertRaises(ValueError):
            self.score()
        self.data["cases"].append(row)
        row["transcript"] = "missing.txt"
        with self.assertRaises(ValueError):
            self.score()

    def test_reused_transcript_paths_cannot_pass(self):
        first, second = self.data["cases"][:2]
        for transcript in (first["transcript"], str(self.path.parent / first["transcript"]),
                           str(Path("alias") / ".." / first["transcript"])):
            with self.subTest(transcript=transcript):
                second["transcript"] = transcript
                with self.assertRaisesRegex(ValueError, "transcript path is reused"):
                    self.score()

    def test_whitespace_transcript_cannot_pass(self):
        row = self.data["cases"][0]
        (self.path.parent / row["transcript"]).write_text(" \n\t\r\n")
        with self.assertRaisesRegex(ValueError, "missing or empty transcript"):
            self.score()

    def test_every_case_needs_review_notes(self):
        row = self.data["cases"][0]
        for notes in (None, "", " \n\t", 1):
            with self.subTest(notes=notes):
                row["notes"] = notes
                with self.assertRaisesRegex(ValueError, "nonempty review notes required"):
                    self.score()
        del row["notes"]
        with self.assertRaisesRegex(ValueError, "nonempty review notes required"):
            self.score()

    def test_passing_cases_cannot_omit_prompt_observations(self):
        for row in self.data["cases"][:10]:
            metric = "checklist_decisions" if row["id"] <= "e05" else "sensitive_questions"
            with self.subTest(case=row["id"], metric=metric):
                original = row[metric]
                row[metric] -= 1
                if metric == "checklist_decisions":
                    row["checklist_agreements"] -= 1
                with self.assertRaisesRegex(ValueError, "passing case must measure at least"):
                    self.score()
                row[metric] = original
                if metric == "checklist_decisions":
                    row["checklist_agreements"] = original

    def test_failed_cases_with_omitted_observations_remain_scoreable(self):
        for row in (self.data["cases"][0], self.data["cases"][5]):
            row.update(passed=False, checklist_decisions=0, checklist_agreements=0, sensitive_questions=0)
        self.assertEqual(self.score()["failures"], ["e01", "e06"])

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

    def test_selected_manifest_requires_matching_hash(self):
        import hashlib
        manifest = Path(self._tmp) / 'manifest.json'
        manifest.write_bytes((ROOT / 'evals/cases.json').read_bytes())
        self.path.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, 'manifest hash'):
            scorer.score(self.path, manifest)
        self.data['manifest_sha256'] = hashlib.sha256(manifest.read_bytes()).hexdigest()
        self.path.write_text(json.dumps(self.data))
        self.assertEqual(scorer.score(self.path, manifest)['cases'], 25)
        manifest.write_text(manifest.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'manifest hash'):
            scorer.score(self.path, manifest)

    def test_default_manifest_rejects_supplied_wrong_hash(self):
        self.data['manifest_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'manifest hash'):
            self.score()
