"""Delivery regressions: installer destinations, CLI JSON and browser PDF failures."""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

from helpers import IsolatedHome, ROOT, fixture
from resuskill_core import cli, jobs, package, profile, render, store
from resuskill_core.util import ResuError


class DeliveryTests(IsolatedHome):
    def cli_json(self, *args, data=None):
        result = subprocess.run(
            [sys.executable, str(ROOT / "skills/resuskill/scripts/resuskill.py"), *args, "--json"],
            input=data, text=True, encoding="utf-8", capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_mutation_commands_honor_json_output(self):
        job_id = self.seed(with_requirements=False)
        jobs.set_requirements(job_id, [])
        self.assertEqual(self.cli_json("job", "show", job_id, "--description"), fixture("job.txt").strip())
        package.propose_resume(job_id, fixture("proposal_good.json"))
        self.assertIsNotNone(self.cli_json("resume", "accept", job_id)["resume"])
        qid = self.cli_json("questions", "add", job_id, "--text", "Why do you want this role?")["id"]
        draft = json.dumps([{"question_id": qid, "text": "I build Python services", "sources": ["summary"]}])
        self.assertEqual(self.cli_json("answers", "propose", job_id, "--file", "-", data=draft)["staged"], [qid])
        self.assertEqual(self.cli_json("answers", "accept", job_id)["accepted"], [qid])
        self.assertEqual(self.cli_json("bank", "save", job_id, qid)["text"], "I build Python services")
        self.assertEqual(self.cli_json("answers", "set", job_id, qid, "--text", "My own answer")["source"], "user")
        email = self.cli_json("questions", "add", job_id, "--text", "What is your email address?")["id"]
        self.assertTrue(self.cli_json("answers", "confirm", job_id, email)["confirmed"])
        extra = self.cli_json("questions", "add", job_id, "--text", "Additional information", "--optional")["id"]
        self.assertEqual(self.cli_json("questions", "categorize", job_id, extra, "sensitive")["category"], "sensitive")
        self.assertTrue(self.cli_json("answers", "set", job_id, extra, "--skip")["skipped"])
        self.assertEqual(self.cli_json("questions", "remove", job_id, extra)["removed"], extra)
        self.assertIn("hash", self.cli_json("package", "approve", job_id)["approval"])

    def test_cli_interrupt_returns_standard_exit_code_without_traceback(self):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), mock.patch.object(cli, "cmd_status", side_effect=KeyboardInterrupt):
            self.assertEqual(cli.main(["status"]), 130)
        self.assertEqual(errors.getvalue(), "error: interrupted\n")

    def test_codex_installer_uses_current_directory_and_explicit_override(self):
        if os.name == "nt" or not shutil.which("bash"):
            self.skipTest("The Bash installer runs on Unix; Windows uses manual copy")
        fake_home = Path(self._tmp) / "friend home"
        env = {**os.environ, "HOME": str(fake_home), "CODEX_HOME": str(fake_home / "old-codex")}
        env.pop("RESUSKILL_CODEX_SKILLS_DIR", None)
        command = ["bash", str(ROOT / "install.sh"), "codex"]
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = fake_home / ".agents/skills/resuskill"
        self.assertTrue(installed.is_symlink())
        self.assertEqual(installed.resolve(), ROOT / "skills/resuskill")
        self.assertFalse((fake_home / "old-codex").exists())
        repeated = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)

        custom = Path(self._tmp) / "custom skills"
        env["RESUSKILL_CODEX_SKILLS_DIR"] = str(custom)
        copied = subprocess.run(command + ["--copy"], env=env, capture_output=True, text=True)
        self.assertEqual(copied.returncode, 0, copied.stderr)
        self.assertFalse((custom / "resuskill").is_symlink())
        version = subprocess.run(
            [sys.executable, str(custom / "resuskill/scripts/resuskill.py"), "--version"],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertIn("resuskill", version.stdout)

    def test_browser_override_expands_user_path_and_rejects_nonexecutables(self):
        executable = Path(self._tmp) / "browser"
        executable.write_text("fake browser", encoding="utf-8")
        executable.chmod(0o700)
        with mock.patch.dict(os.environ, {"HOME": self._tmp, "USERPROFILE": self._tmp, "RESUSKILL_BROWSER": "~/browser"}):
            self.assertEqual(render.find_browser(), str(executable.resolve()))
        with mock.patch.dict(os.environ, {"RESUSKILL_BROWSER": self._tmp}), mock.patch.object(render.shutil, "which", return_value=None):
            self.assertIsNone(render.find_browser())
        if os.name != "nt":
            executable.chmod(0o600)
            with mock.patch.dict(os.environ, {"RESUSKILL_BROWSER": str(executable)}):
                self.assertIsNone(render.find_browser())

    def test_windows_browser_search_does_not_use_missing_environment_roots(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(render.platform, "system", return_value="Windows"), \
                mock.patch.object(render.shutil, "which", return_value=None), mock.patch.object(Path, "is_file", return_value=True) as is_file:
            self.assertIsNone(render.find_browser())
            is_file.assert_not_called()


class PdfDeliveryTests(IsolatedHome):
    COMPLETE = b"%PDF-1.4\nexample output\n%%EOF\n"

    def setUp(self):
        super().setUp()
        self.html = Path(self._tmp) / "resume.html"
        self.html.write_text("<h1>Example</h1>", encoding="utf-8")
        self.pdf = Path(self._tmp) / "resume.pdf"
        self.pdf.write_bytes(b"previous PDF")

    def browser(self, content, proc=None):
        proc = proc or mock.Mock()
        proc.poll.return_value = 0

        def start(command, **kwargs):
            self.output = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--print-to-pdf=")))
            self.output.write_bytes(content)
            return proc

        return mock.patch.object(render.subprocess, "Popen", side_effect=start)

    def test_failed_or_truncated_print_preserves_existing_pdf(self):
        for content in (b"", b"browser error", b"%PDF-1.4\npartial", b"not a PDF\n%%EOF"):
            with self.subTest(content=content), mock.patch.object(render, "find_browser", return_value="browser"), self.browser(content):
                with self.assertRaisesRegex(ResuError, "complete PDF"):
                    render.print_pdf(self.html, self.pdf)
                self.assertEqual(self.pdf.read_bytes(), b"previous PDF")
                self.assertFalse(self.output.parent.exists())

    def test_successful_print_replaces_existing_pdf(self):
        with mock.patch.object(render, "find_browser", return_value="browser"), self.browser(self.COMPLETE):
            self.assertEqual(render.print_pdf(self.html, self.pdf), self.pdf)
        self.assertEqual(self.pdf.read_bytes(), self.COMPLETE)
        self.assertFalse(self.output.parent.exists())

    def test_browser_launch_failure_preserves_existing_pdf(self):
        with mock.patch.object(render, "find_browser", return_value="browser"), \
                mock.patch.object(render.subprocess, "Popen", side_effect=OSError("launch failed")):
            with self.assertRaises(OSError):
                render.print_pdf(self.html, self.pdf)
        self.assertEqual(self.pdf.read_bytes(), b"previous PDF")
        self.assertEqual(sorted(p.name for p in Path(self._tmp).iterdir()), ["resume.html", "resume.pdf"])

    def test_a_paused_partial_write_is_not_treated_as_finished(self):
        proc = mock.Mock()
        proc.poll.return_value = None
        sleeps = 0

        def resume_write(_delay):
            nonlocal sleeps
            sleeps += 1
            if sleeps == 3:
                self.output.write_bytes(self.COMPLETE)

        with mock.patch.object(render, "find_browser", return_value="browser"), self.browser(b"%PDF-1.4\npartial", proc), \
                mock.patch.object(proc, "poll", return_value=None), mock.patch.object(render.time, "sleep", side_effect=resume_write):
            render.print_pdf(self.html, self.pdf)
        self.assertGreaterEqual(sleeps, 3)
        self.assertEqual(self.pdf.read_bytes(), self.COMPLETE)
        proc.terminate.assert_called_once()
        proc.wait.assert_called_once_with(timeout=5)

    def test_timeout_reaps_browser_and_keeps_existing_pdf(self):
        proc = mock.Mock()
        proc.wait.side_effect = [subprocess.TimeoutExpired("browser", 5), 0]
        with mock.patch.object(render, "find_browser", return_value="browser"), self.browser(b"%PDF-1.4\npartial", proc), \
                mock.patch.object(proc, "poll", return_value=None), mock.patch.object(render.time, "monotonic", side_effect=[0, 91]):
            with self.assertRaisesRegex(ResuError, "complete PDF"):
                render.print_pdf(self.html, self.pdf)
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()
        self.assertEqual(proc.wait.call_args_list, [mock.call(timeout=5), mock.call()])
        self.assertEqual(self.pdf.read_bytes(), b"previous PDF")

    def test_interrupt_reaps_browser_and_keeps_existing_pdf(self):
        proc = mock.Mock()
        with mock.patch.object(render, "find_browser", return_value="browser"), self.browser(b"%PDF-1.4\npartial", proc), \
                mock.patch.object(proc, "poll", return_value=None), mock.patch.object(render.time, "sleep", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                render.print_pdf(self.html, self.pdf)
        proc.terminate.assert_called_once()
        proc.wait.assert_called_once_with(timeout=5)
        self.assertEqual(self.pdf.read_bytes(), b"previous PDF")
        self.assertFalse(self.output.parent.exists())

    def test_failed_reprint_keeps_previous_pdf_and_its_provenance(self):
        job_id = self.seed()
        package.propose_resume(job_id, fixture("proposal_good.json"))
        package.accept_resume(job_id)
        prof = profile.load()
        pdf = render.out_dir(job_id) / render.pdf_name(prof)
        pdf.write_bytes(self.COMPLETE)
        stamp = render.stamp_path(pdf)
        store.write_json(stamp, render.pdf_stamp(prof, package.load(job_id)["resume"]))
        before = stamp.read_bytes()
        with mock.patch.object(render, "print_pdf", side_effect=ResuError("browser failed")):
            with self.assertRaises(ResuError):
                render.render(job_id, want_pdf=True)
        self.assertEqual(pdf.read_bytes(), self.COMPLETE)
        self.assertEqual(stamp.read_bytes(), before)
