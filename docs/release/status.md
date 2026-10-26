# Public beta qualification

Status: **NOT QUALIFIED — do not publish a beta tag yet.**

Baseline implementation: 0e5c83c. Subsequent milestones require qualification on their own exact release revision.

## Initial milestone A checkpoint (historical)

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

## Implementation checkpoint through milestone G (historical)

The feature sequence is implemented in separate verified commits: follow-ups, historical outcomes, reviewed imports, explicit copy migration/pinned evidence, cover letters and interview stories. Milestone A qualification infrastructure is implemented; public qualification is incomplete.

At that checkpoint, local suite: **357 passing tests**, Python 3.14.1. Copied-install smoke passes outside the checkout and now exercises migration, follow-ups, historical insights, letters and stories. Independent reviews completed for each feature; all confirmed findings were fixed and rechecked. Detailed evidence is in `docs/verification/04-beta-qualification.md` through `10-stories.md`.

Current behavioral manifest: `evals/cases-v7.json`, **34 cases per client** (original 25 unchanged). Human-reviewed passes on the final implementation: **0/34 Codex and 0/34 Claude Code**; this indicates missing qualification evidence, not 68 observed behavioral failures. Earlier launch failures/ungraded captures remain recorded above. At that checkpoint, remote CI and visual inspection were pending; the later CI result is recorded below. No beta tag was published.

Current limitations: source checks cannot prove meaning, authorship or business impact; explicit user review remains necessary. Git evidence supports regular UTF-8 committed files up to 2 MB. Job ingestion is reviewed JSON only. Follow-ups are manual calendar records without notification scheduling or messages. Letters use sourced factual paragraphs with fixed nonfactual openings/closings; company research is not included. Story suggestions show skill overlap, not full requirement satisfaction. PDF export requires a supported local browser. Format 2 requires a new-directory migration and fresh package approvals; incomplete imports must be recovered first, and import previews regenerated after migration.

## Qualification update — 2026-10-25

Candidate code revision: **4c53ecd8c2f44a19532eeaceaef74bec601f7891**. All nine Linux/macOS/Windows × Python 3.9/3.11/3.13 jobs passed, including CLI and copied-install checks: [CI run 40119706013](https://github.com/Varunsai1930/ResuSkill/actions/runs/40119706013). The previous Windows failure was corrected by explicitly reading UTF-8 artifacts in three tests; no assertions were weakened. Local suite: **379 tests passed**. Independent review covered the later fixes and the encoding correction; see `docs/verification/11-windows-encoding.md`. The fix was pushed with explicit user approval; no release tag was published.

Behavioral captures use revision 7484544; its skill tree is identical to 4c53ecd (Git tree 068d383dfaa8efb1c9ebc0e8f66e9d27b43df740). Preserve that actual revision in results. Captures and review materials now live outside temporary storage at `/Users/varun/.codex/visualizations/2026/10/21/01a15c6a-13e4-7322-8693-a0adb8de3e57/resuskill-eval-7484544/`. Captures are ungraded, not passes. Failed usage-limit attempts and timeouts remain retained; retries use separate folders. Claude Code is still signed out as of this update. Complete staged conversations, model identity, human semantic review and visual inspection remain unresolved release gates.

User decision on 2026-10-25: leave Claude evaluation blocked and human review pending. These gates are deferred, not waived, and no model-generated score replaces them.

## Capture update — 2026-10-26

Codex now has **31/34 distinct case IDs with completed one-turn captures**, aggregated across retained attempts. Cases **e29 (follow-ups), e30 (historical outcomes) and e31 (reviewed imports)** still lack a completed capture: the latest attempts failed at the client usage limit, and the batch stopped after three consecutive failures. No capture process remains running. Completion records successful client execution only; **0/34 human-reviewed Codex passes** are recorded. Claude remains blocked by user decision, with **0/34 human-reviewed passes**. Neither denominator is a claim of observed behavioral failures.

Fresh retry workspaces retain revision `4c53ecd-dirty`, reflecting documentation-only changes during preparation; do not relabel them as clean-revision runs. The manifest remains `evals/cases-v7.json` (SHA-256 `539c401a44e80b859f8bbe82dbddd34fc99c26e5ac93db41f9d1dbe989d5ac21`). Captures report Codex CLI 0.154.0 but no model identity. The evidence overview, transcripts, artifact inventories and unfilled review templates are retained at `/Users/varun/.codex/visualizations/2026/10/21/01a15c6a-13e4-7322-8693-a0adb8de3e57/resuskill-evaluation-overview.md`. Original failures and retries remain separate.

The PDF case captured an explicit browser failure; a completed agent response does not establish a successful PDF export or visual inspection. Complete staged conversations, model identity, human review, Claude evaluation and visual inspection remain release blockers. No beta tag was created.

Documentation verification: independent Code Reviewer found no actionable accuracy issues in the qualification update and independently confirmed the identical skill-tree hashes. Final capture counts were derived from retained case metadata; `git diff --check` passed. This documentation-only update does not change the code covered by the 379-test local result or nine passing CI jobs.
