# Public beta qualification

Status: **NOT QUALIFIED — do not publish a beta tag yet.**

Baseline implementation: 0e5c83c. Subsequent milestones require qualification on their own exact release revision.

- Local automated suite: 311 tests passed for the initial milestone A changes (Python 3.14.1).
- Copied-install smoke: passed locally; CI now runs it on Linux/macOS/Windows with Python 3.9/3.11/3.13. Remote matrix results have not been obtained.
- Behavioral suite: original 25 cases preserved; v2 has 28 cases per client. Prepared fictional workspaces at `/private/tmp/resuskill-beta-evals`; preparation is not execution or grading.
- Claude Code: installed, but `claude auth status` reports signed out. Runs blocked until the user signs in.
- Codex: e26 failed loading local MCP transport configuration; e27 with default configuration failed because the sandbox denied runtime-state writes. Neither is a behavioral pass. An authorized e28 retry completed, but remains ungraded and pending human review. Its final response includes an assumption that the job remains open; a human must assess that against the case expectation.
- Human semantic review: pending for both clients. No scores or approval decisions have been fabricated.
- Independent Code Reviewer audit completed for the original three features with no confirmed finding. It found a manifest-hash bypass in the new scorer default path; fixed and regression-tested; independent recheck passed with no unresolved confirmed finding.
- Visual review of short, long and multilingual HTML/PDF: pending. Earlier browser inspection rejected local file URLs; no bypass is authorized.
- Publishing: separate step after all release gates pass. No tag or push performed.

## Required release evidence

Record exact revision/diff, client/model versions, manifest hash, human reviewer, transcripts, artifacts and scored denominators. Both client suites must pass; review incomplete staged conversations with the actual user, never scripted approval of unseen content. New features extend the versioned suite. Run full CI and copied-install/export checks on the candidate release revision. Publish only after reviewing all results.

Codex captures against committed 99aebc5: e01–e03 failed due to the account usage limit; the runner stopped after three failures. Remaining cases are not run, and no behavioral score is reported.
