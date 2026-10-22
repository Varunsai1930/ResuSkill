# Changelog

## Unreleased

- Add offline reviewed shortlist previews and explicit application of selected rows, with duplicate detection, stale-preview rejection and resumable import journals.

- Add historical submission cohorts with separate current-status, reached-stage and frozen-fit denominators; disclose incomplete history and suppress small-sample percentages.

- Add manual dated follow-ups with preserved completion history and terminal-state suppression; serialize CLI data operations with an explicit local lock.

- Add isolated copied-install smoke checks to the CI matrix and versioned behavioral case manifests with hash-bound scoring; preserve the original 25-case baseline.
- Add claim-source review, recurring-gap/outcome reports and the local pipeline overview. Public beta qualification remains pending; see docs/release/status.md.

- Reject malformed job evidence, overrides and question metadata before checklist or review code reads it. Preserve legacy evidence records that predate source hashes.

- Validate stored profile structures and metadata before using them. Damaged or unnormalized records produce recovery errors without regenerating IDs, changing facts or overwriting data.

- Validate stored proposal records at the shared read boundary. Malformed metadata or resume fields now produce recovery errors across show, render, batch and ATS commands without partial exports or record changes.

- Revalidate the selected resume against current sources before rendering. Reject stale unsupported claims before replacing prior HTML, styling or PDFs.

- Fix ATS PDF comparison accepting changed decimals, signs and contact separators after punctuation was discarded. Preserve meaningful punctuation and word boundaries while normalizing whitespace and typographic variants.

- Add read-only `ats` preflight for current-source validation, required/preferred keyword groups with any/all semantics, evidence-backed omissions, contact/structure warnings and optional actual-PDF text checks. Keep unknowns explicit and avoid ATS-score or hiring predictions.

- Add `batch-export` for selected pending proposals or accepted resumes: validate all drafts first, produce an index/report/ZIP, preserve approval state, and report PDF failures with HTML fallback.

- Record job observations, deadlines, intake dates and conditional eligibility with `job observe`. Show stale/closed/expired/unverified states separately from application tracking, while keeping legacy jobs readable and historical tracking available.

- Add validated, reusable resume styling (`render --style`), a navy preset, section ordering and degree-first education. Keep facts separate from presentation and include styling in PDF snapshot provenance.

- Explain PDF launch failures, browser exit codes, timeouts and likely permission/library issues without exposing browser logs. Retain HTML fallback and existing-PDF preservation.

- Add `doctor` setup diagnostics and an optional fictional PDF smoke test; explain missing profile/browser setup and keep local task outputs out of Git.

- Keep the user's own skill and technology spelling ("REST APIs", "Pandas") in the profile and on the resume; matching still ignores spelling. Group uncategorized resume skills last as "Other". Print labelled grades ("CGPA: 8.88/10", "Score: 986/1000") as written. Keep each contact item on one line.
- Repository ranking: keep forks (listed last, with a note) instead of hiding them; recognise "Jupyter Notebook" repositories; ignore GitHub error bodies passed as READMEs; match profile links that point inside a repository; print untrusted repository text as single lines; show technology names as written; compile one term set per run.
- Add an isolated Codex evidence runner for all 25 behavior cases, with hidden expectations, explicit execution status, JSONL transcripts and artifact hashes. Keep all grading pending human review, and tighten scoring to reject reused/blank transcripts and missing case observations.
- Improve job finding: explicit `--level`, preserve management/mid-level targets and avoid entry-level inference after additional degrees; separate student alternatives, use two confirmed skills plus broader job queries, verify and deduplicate employer postings, and read public JavaScript pages with an available browser. Generate capped plans lazily without allocating the full role/location product.
- Add GitHub project suggestions: the agent asks for GitHub and LinkedIn links, fetches all public repository pages, and `job repos` ranks them offline against the job (required and custom skills weigh more; lowercase topics are recognized; forks/empty repos skipped; README-only mentions kept separate and weaker). Malformed language/API fields are rejected. Projects reach a resume only after the user confirms them into the profile. LinkedIn content comes from a PDF the user saves, never from reading the site.
- Recognise Greenhouse's default authorization wording ("Do you now, or will you in the future, require visa sponsorship ...", "Are you currently eligible to work in the United States of America?") as profile-backed questions instead of sensitive ones.
- Count using a SQL database (PostgreSQL, MySQL, SQLite ...) as evidence for an already confirmed SQL skill when ranking search skills, so SQL is no longer ranked last.
- Remote searches name each country the user is authorized to work in (`Remote United States`), since a bare "Remote" mostly returned postings from other countries. SKILL.md tells the agent to open job-board search pages and list only individual postings.
- Harden search terms: omit contact-address fallbacks, preserve remote-only filters with explicit locations, leave ambiguous graduation dates/levels Unknown, and prioritize ongoing/recent roles using available dates. Add regression coverage and align the agent instructions and command reference.
- Add job finding: `profile search-terms` builds offline search queries from confirmed profile skills (ranked by supporting entries), roles, locations, work mode and graduation level, without contact details. SKILL.md tells the agent to search with its own web tool, list only postings it actually found, mark unopened ones unverified and save only postings the user picks.
- Preserve distinct IDs for duplicate profile entries, bullets and requirements when unchanged input is saved again; reserve explicitly supplied IDs before matching implicit ones. Reject malformed bullet IDs.
- Keep availability Unknown when a job gives only its earliest start and the candidate is available later. Reject reversed availability/graduation date windows and share their date-validation logic.
- Prevent legacy authorization/sponsorship questions stored as ordinary factual questions from bypassing confirmation. Validation policy v5 makes earlier approvals stale.
- Report damaged package fields and unreadable input/storage as recovery errors; apply the same duplicate-key/nonfinite-number checks to stored JSON as to incoming JSON.
- Preserve existing PDFs and their provenance on failed exports; replace them only after a new PDF has a header and final trailer. Validate browser overrides and honor `--json` on mutation commands.
- Install Codex skills in the current `~/.agents/skills/` location, with `RESUSKILL_CODEX_SKILLS_DIR` for custom paths. Refresh newcomer instructions, remove the obsolete implementation plan, and remove unreachable profile/factual-answer branches and unnecessary education sorting.
- Restrict AI answers to a small allow-list of writing prompts; unclear questions accept the user's answer directly. Use complete field labels for automatic factual answers.
- Validate JSON shapes before writes, with field paths; reject duplicate keys, non-finite numbers, duplicate answer IDs and invalid booleans.
- Require explicit sources for AI answers, and bullet sources for resume bullets. Do not implicitly use the entire profile summary as evidence.
- Revalidate accepted answers and submission snapshots. Invalidate older-policy approvals, changed evidence and stale overrides. Require a requirements review before approval.
- Check factual answer limits and real calendar dates; do not infer sponsorship eligibility from an employer's willingness to sponsor.
- Show source text and replacement drafts in the answer review, and disclose all imported profile bullets in the initial diff.
- Add an isolated `demo` command, schema-version guards, installer error handling, regression tests and a 25-case human-reviewed agent evaluation pack.
- Treat CPA, PMP, CFA, CISSP and CCNA as separate credentials, by acronym or full name. A source that shows a credential in progress (candidate, pursuing, preparing, a CFA level) does not support a claim of holding it.
- Decide whether a degree is completed or being pursued only when its end date is clearly past or future; a year or month that includes today stays unknown. Dates compare against the local calendar day.
- Keep certification IDs when unchanged input is saved again or a date is corrected; a certification from a different issuer gets a new ID.
- Answer work-authorization and sponsorship questions worded "now or in the future" or "for any employer" from the matching country record.
- List damaged or mismatched job files as unreadable in `jobs` instead of failing; an empty or partial package file reads as an empty draft.

Compatibility: schema stays at v1. Existing profile/job data is retained. Existing approvals (including those made before the credential changes) and legacy evidence/overrides may need renewed review. A job folder whose `job.json` id differs from the folder name is refused. Strict validation can reject previously accepted malformed input. Unknown prompt wording now requires user input. `evidence link` replaces its set of sources, and `package check` returns nonzero for blockers.

Known limits: deterministic lexical checks cannot establish semantic truth, catch every technology or prevent an agent from bypassing the workflow. Agent behavior in both clients must be evaluated separately. No zero-hallucination guarantee is made.

- Added explicit copy migration to data format 2 and pinned local Git evidence with separate candidate contribution/outcome attestations, confirmation, refresh and retirement.

- Added optional sourced cover letters with separate pending/accepted content, approval freshness, frozen submission evidence, staged HTML/PDF exports and source review. Snapshot writes now stage before publication.

- Added sourced interview stories with explicit unknown results and contribution scope, separate drafts/accepted stories, freshness checks, pinned-code questions, job-specific skill overlap and staged HTML/JSON exports.
