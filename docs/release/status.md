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

## Implemented through milestone G

The feature sequence is implemented in separate verified commits: follow-ups, historical outcomes, reviewed imports, explicit copy migration/pinned evidence, cover letters and interview stories. Milestone A qualification infrastructure is implemented; public qualification is incomplete.

Latest local suite: **357 passing tests**, Python 3.14.1. Copied-install smoke passes outside the checkout and now exercises migration, follow-ups, historical insights, letters and stories. Independent reviews completed for each feature; all confirmed findings were fixed and rechecked. Detailed evidence is in `docs/verification/04-beta-qualification.md` through `10-stories.md`.

Current behavioral manifest: `evals/cases-v7.json`, **34 cases per client** (original 25 unchanged). Human-reviewed passes on the final implementation: **0/34 Codex and 0/34 Claude Code**; this indicates missing qualification evidence, not 68 observed behavioral failures. Earlier launch failures/ungraded captures remain recorded above. Nine remote OS/Python jobs and visual short/long/multilingual HTML/PDF review have no completed final-revision evidence. No beta tag, push or publication has occurred.

Current limitations: source checks cannot prove meaning, authorship or business impact; explicit user review remains necessary. Git evidence supports regular UTF-8 committed files up to 2 MB. Job ingestion is reviewed JSON only. Follow-ups are manual calendar records without notification scheduling or messages. Letters use sourced factual paragraphs with fixed nonfactual openings/closings; company research is not included. Story suggestions show skill overlap, not full requirement satisfaction. PDF export requires a supported local browser. Format 2 requires a new-directory migration and fresh package approvals; incomplete imports must be recovered first, and import previews regenerated after migration.
