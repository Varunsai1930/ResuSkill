# Changelog

## Unreleased

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
