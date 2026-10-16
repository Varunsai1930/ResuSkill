"""Exercise evidence preparation/capture with fake processes, never model requests."""

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

from helpers import IsolatedHome, ROOT

spec = importlib.util.spec_from_file_location("eval_runner", ROOT / "evals/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class EvalRunnerTests(IsolatedHome):
    def prepare(self, cases=("e01", "e19")):
        return runner.prepare(Path(self._tmp) / "prepared", cases)

    def test_independent_homes_hidden_expectations_and_unsaved_import(self):
        output = self.prepare()
        first = output / "e01/workspace"
        second = output / "e19/workspace"
        self.assertTrue((first / "home/profile.json").is_file())
        self.assertFalse((second / "home/profile.json").exists())
        self.assertTrue((second / "inputs/resume.txt").is_file())
        self.assertTrue((first / ".agents/skills/resuskill/SKILL.md").is_file())
        expected = json.loads((output / "reviewer/e01.json").read_text())["expected"]
        for workspace in (first, second):
            self.assertFalse(any(path.name == "cases.json" for path in workspace.rglob("*")))
            self.assertFalse(any(expected in path.read_text(errors="replace")
                                 for path in workspace.rglob("*") if path.is_file()))
        review = json.loads((output / "review-template.json").read_text())
        self.assertTrue(all(row["passed"] is None and row["claims"] is None for row in review["cases"]))

    def test_refuses_reused_output_and_unknown_case(self):
        output = self.prepare()
        with self.assertRaises(FileExistsError):
            runner.prepare(output)
        with self.assertRaises(ValueError):
            runner.prepare(Path(self._tmp) / "unknown", ["e99"])

    def test_new_job_identity_preserves_case_input_without_leaking_expectations(self):
        selected = ("e01", "e02", "e03", "e04", "e05", "e13", "e17", "e18", "e23")
        output = self.prepare(selected)
        for ident in selected:
            case = json.loads((output / "reviewer" / f"{ident}.json").read_text())
            prompt = (output / ident / "prompt.txt").read_text()
            self.assertTrue(prompt.endswith("\nRequest:\n" + case["prompt"] + "\n"))
            self.assertNotIn(case["expected"], prompt)
            self.assertNotIn('"expected"', prompt)
            self.assertFalse((output / ident / "workspace/home/jobs").exists())
            if ident == "e23":
                self.assertIn("Demo Corp, Backend Engineering Intern, Austin, TX, and inputs/job.txt", prompt)
                self.assertNotIn('title "Example role"', prompt)
            else:
                self.assertIn('company "Demo Corp" and title "Example role"', prompt)
                self.assertIn("description is the exact job text in the request below", prompt)

    def test_staged_cases_have_real_cli_prerequisites(self):
        output = self.prepare(("e20", "e21", "e22", "e24", "e25"))
        rejected = (output / "e20/workspace/setup.txt").read_text()
        self.assertIn('"returncode": 1', rejected)
        e21 = list((output / "e21/workspace/home/jobs").glob("*/package.json"))[0]
        pending = json.loads(e21.read_text())
        self.assertTrue(pending["answer_proposals"])
        self.assertEqual(pending["answers"], {})
        e22 = json.loads((output / "e22/workspace/home/profile.json").read_text())
        self.assertFalse(any("1,200" in str(bullet) for bullet in e22["experience"][0]["bullets"]))
        e24 = list((output / "e24/workspace/home/jobs").glob("*/package.json"))[0]
        self.assertTrue(json.loads(e24.read_text())["approval"])

    def test_failed_run_captures_evidence_without_a_passing_result(self):
        output = self.prepare(("e01",))
        process = type("FailedProcess", (), {"returncode": 7, "communicate": lambda self, *a, **kw: None})()
        version = subprocess.CompletedProcess(["fake-codex", "--version"], 0, "codex-cli test\n", "")
        with patch.object(runner.subprocess, "Popen", return_value=process) as launch, \
                patch.object(runner.subprocess, "run", return_value=version):
            result = runner.run_case(output / "e01", codex="fake-codex")
        self.assertEqual(result["execution_status"], "failed")
        self.assertIsNone(result["passed"])
        self.assertEqual(result["returncode"], 7)
        self.assertEqual(result["client_version"], "codex-cli test")
        self.assertIsNone(result["model"])
        args = launch.call_args.args[0]
        self.assertIn("workspace-write", args)
        self.assertFalse(any("bypass" in arg or arg == "--model" for arg in args))
        evidence = output / "e01/evidence"
        self.assertTrue((evidence / "before.json").is_file())
        self.assertTrue((evidence / "after.json").is_file())
        self.assertTrue((evidence / "transcript.txt").is_file())
        artifacts = json.loads((evidence / "artifacts.json").read_text())
        self.assertIn("transcript.txt", artifacts)
        self.assertNotIn("artifacts.json", artifacts)
        review = json.loads((output / "review-template.json").read_text())
        self.assertIsNone(review["cases"][0]["passed"])
        with self.assertRaises(ValueError):
            runner.run_case(output / "e01", codex="fake-codex")

    def test_mcp_overrides_preserve_model_and_use_only_table_names(self):
        config = Path(self._tmp) / "config.toml"
        config.write_text('model = "configured-model"\n[mcp_servers.graph]\ncommand = "secret"\n'
                          '[mcp_servers."with-dash"] # comment\nurl = "private"\n')
        overrides = runner.mcp_overrides(config)
        self.assertEqual(overrides, ["-c", "mcp_servers.\"graph\".enabled=false",
                                    "-c", "mcp_servers.\"with-dash\".enabled=false"])
        self.assertNotIn("secret", str(overrides))

    def test_literal_quoted_mcp_names_work_with_and_without_tomllib(self):
        config = Path(self._tmp) / "config.toml"
        config.write_text("[mcp_servers.'single-quoted']\ncommand = 'server'\n"
                          '[mcp_servers."double.quoted"]\ncommand = "server"\n'
                          '[mcp_servers.bare]\ncommand = "server"\n')
        expected = ["-c", 'mcp_servers."bare".enabled=false', "-c",
                    'mcp_servers."double.quoted".enabled=false', "-c",
                    'mcp_servers."single-quoted".enabled=false']
        self.assertEqual(runner.mcp_overrides(config), expected)
        with patch.object(runner, "tomllib", None):
            self.assertEqual(runner.mcp_overrides(config), expected)

    def test_timeout_is_captured_and_terminates_the_process_group(self):
        output = self.prepare(("e01",))
        process = type("Process", (), {"returncode": -15, "pid": 123})()
        process.communicate = Mock(
            side_effect=[subprocess.TimeoutExpired("fake", 1), None])
        version = subprocess.CompletedProcess(["fake-codex", "--version"], 0, "codex-cli test", "")
        with patch.object(runner.subprocess, "Popen", return_value=process), \
                patch.object(runner.subprocess, "run", return_value=version), \
                patch.object(runner, "POSIX", True), \
                patch.object(runner.os, "killpg", create=True) as kill:
            result = runner.run_case(output / "e01", timeout=1, codex="fake-codex")
        self.assertEqual(result["execution_status"], "timed_out")
        kill.assert_called_once_with(123, runner.signal.SIGTERM)

    def test_windows_cleanup_uses_process_methods(self):
        process = Mock()
        with patch.object(runner, "POSIX", False):
            runner.stop_process(process)
            runner.stop_process(process, force=True)
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()

    def test_interrupt_stops_its_child_before_recording_finished_status(self):
        output = self.prepare(("e01",))
        process = Mock(returncode=-15)
        process.communicate.side_effect = [KeyboardInterrupt(), None]
        version = subprocess.CompletedProcess(["fake-codex", "--version"], 0, "codex-cli test", "")
        with patch.object(runner.subprocess, "Popen", return_value=process), \
                patch.object(runner.subprocess, "run", return_value=version), \
                patch.object(runner, "POSIX", False):
            result = runner.run_case(output / "e01", codex="fake-codex")
        process.terminate.assert_called_once_with()
        self.assertEqual(process.communicate.call_count, 2)
        self.assertEqual(result["execution_status"], "interrupted")
        self.assertEqual(result["returncode"], -15)
        self.assertTrue(result["process_stopped"])
        self.assertIsNotNone(result["finished_at"])
        self.assertIsNone(result["passed"])

    def test_default_config_does_not_invent_model_or_mcp_transports(self):
        output = self.prepare(("e01",))
        process = Mock(returncode=0)
        version = subprocess.CompletedProcess(["fake-codex", "--version"], 0, "codex-cli test", "")
        with patch.object(runner.subprocess, "Popen", return_value=process) as launch, \
                patch.object(runner.subprocess, "run", return_value=version), \
                patch.object(runner, "mcp_overrides") as overrides:
            result = runner.run_case(output / "e01", codex="fake-codex", default_config=True)
        overrides.assert_not_called()
        self.assertIn("--ignore-user-config", launch.call_args.args[0])
        self.assertEqual(result["config_mode"], "client_defaults")
        self.assertIsNone(result["model"])

    def test_records_only_observed_model_name(self):
        evidence = Path(self._tmp)
        (evidence / "events.jsonl").write_text('{"type":"session_meta","payload":{"model":"actual-model"}}\n')
        self.assertEqual(runner.observed_model(evidence), "actual-model")

    def test_success_captures_client_output_but_leaves_review_pending(self):
        output = self.prepare(("e01",))
        version = subprocess.CompletedProcess(["fake-codex", "--version"], 0, "codex-cli test", "")

        def launch(command, **kwargs):
            kwargs["stdout"].write(b'{"type":"session_meta","payload":{"model":"actual-model"}}\n')
            Path(command[command.index("--output-last-message") + 1]).write_text("Concrete draft awaiting approval.")
            return Mock(returncode=0)

        with patch.object(runner.subprocess, "Popen", side_effect=launch), \
                patch.object(runner.subprocess, "run", return_value=version):
            result = runner.run_case(output / "e01", codex="fake-codex")
        self.assertEqual(result["execution_status"], "completed")
        self.assertEqual(result["model"], "actual-model")
        self.assertIsNone(result["passed"])
        self.assertEqual(result["review_status"], "pending_human_review")
        self.assertIn("Concrete draft awaiting approval.", (output / "e01/evidence/transcript.txt").read_text())
