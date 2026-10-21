# ResuSkill CLI reference

`$RS` below means `python3 "<skill-dir>/scripts/resuskill.py"`; expand it as that command, not a shell string variable. Add `--json` to most read commands for machine-readable output. Commands exit `0` on success, `1` on rejection or a blocked package check, and `2` for invalid command syntax. JSON validation errors include field paths and do not replace existing data. `package check --json` emits blockers on stdout with exit code 1; other rejected commands print `error:` on stderr.

## Overview
| Command | Purpose |
|---|---|
| `$RS status` | Data directory, profile revision, job count, PDF browser |
| `$RS doctor [--pdf-smoke] [--json]` | Check setup without changing candidate data; optional browser smoke test uses temporary fictional content. Errors exit 1; missing optional browser/profile are warnings |
| `$RS demo [--output NEW_DIR] [--json]` | Create a fictional draft and review HTML in an isolated new directory; never use the real profile |
| `$RS jobs` | Tracker table: review state, status, checklist counts |

## Profile
| Command | Purpose |
|---|---|
| `$RS profile template` | Print the profile skeleton |
| `$RS profile show [--json]` | Show the profile with entry and bullet IDs |
| `$RS profile diff --file F` | Validate and list changes **without saving** |
| `$RS profile save --file F` | Validate, keep IDs, bump revision, archive old version (only after user confirms) |
| `$RS profile search-terms [--role R]... [--location L]... [--skill S]... [--level LEVEL] [--max-queries N]` | Offline: job-search queries plus ranked confirmed skills, level hint, skills not held and sponsorship needs. Roles default to `preferences.roles`, then the two most recent job titles (ongoing first). Locations come from `--location` or `preferences.locations`; contact addresses are never used. Missing search locations prompt a warning. `any` adds a Remote alternative by default; `remote` searches Remote by default and keeps a Remote filter with explicit locations. Remote searches say `Remote <country>` for each country the user is authorized to work in (plain `Remote` when none is known). Graduation dates that include today or additional degrees after a completed bachelor’s leave the level Unknown. `--level` sets a user-requested level for roles without one (`student`, `intern`, `entry`, `junior`, `mid`, `senior`, `lead`, `manager`, `director`, `any`); `any` omits inferred filters. Titles with their own level keep it. `--skill` accepts only confirmed profile skills. Focused queries default to the top 2; broader queries omit skills, and all queries include job-search intent. Pick 1–2 role-relevant skills explicitly when evidence frequency favors unrelated tools. Student searches use separate internship and entry-level queries, with a first pass across roles/locations before alternative levels. Warns when the query cap leaves queries out. |

## Jobs and checklist
| Command | Purpose |
|---|---|
| `$RS job add --company C --title T --description-file F [--location L] [--url U]` | Save a job description (`F` may be `-`) |
| `$RS job show JOB [--description]` | Job details, requirements, questions; `--description` prints the full text |
| `$RS job repos JOB --file F` | Offline: rank GitHub repositories (the `/users/<name>/repos` JSON the agent fetched, optional `readme`/`languages` per repo) by the job's technologies. Skips empty repos, lists forks last with a note, marks repos already in the profile (links inside a repo still match), keeps README-only mentions separate, flags notebook repos, ignores README text that is a GitHub error response, and prints repository text as single lines. Stores nothing |
| `$RS job requirements JOB --file F` | Save the reviewed requirement list (all-or-nothing; excerpts must be verbatim) |
| `$RS job observe JOB --file F` | Replace reviewed listing status, verification timestamp/source, deadline, program dates and conditional eligibility. Offline; shows age/expiry warnings and invalidates older approval |
| `$RS checklist JOB` | Deterministic Met / Unmet / Unknown with basis and evidence |
| `$RS evidence link JOB REQ SOURCE...` | Replace the requirement's evidence with all currently user-confirmed source IDs; changes invalidate approval |
| `$RS evidence unlink JOB REQ` | Remove evidence links |
| `$RS override JOB REQ --status met\|unmet\|unknown\|clear --reason "..."` | User correction with a recorded reason |

## Resume
| Command | Purpose |
|---|---|
| `$RS resume propose JOB --file F [--model NAME]` | Validate and store a proposal (does not change the accepted resume) |
| `$RS resume show JOB [--proposal]` | Show the accepted resume or the pending proposal with sources |
| `$RS resume accept JOB` | Make the stored proposal the accepted resume (clears approval) |

## Questions and answers
| Command | Purpose |
|---|---|
| `$RS questions add JOB --text "..." [--optional] [--limit N] [--unit chars\|words] [--category C]` | Add a question; the category is detected by rules |
| `$RS questions list JOB` | Every question with its current answer and label |
| `$RS questions categorize JOB QID factual\|sensitive_factual\|sensitive\|open` | Set the category; only allow-listed writing prompts can be open, and sensitive categories cannot be weakened |
| `$RS questions remove JOB QID` | Remove a question |
| `$RS answers propose JOB --file F [--model NAME]` | Store AI drafts for **open** questions (validated, pending review) |
| `$RS answers accept JOB [QID...]` | Accept pending drafts (all when no IDs) |
| `$RS answers set JOB QID --text "..." \| --file F \| --skip` | Store the user's own answer, or skip an optional question |
| `$RS answers confirm JOB QID` | User confirms the profile value (factual / sensitive_factual) |
| `$RS bank save JOB QID` | Save an accepted answer to a recognised open writing prompt for reuse |
| `$RS bank list` | List saved answers |

Answer labels: **From profile**, **AI draft**, **User answer**, **Missing information**, **User input required**, **AI draft (pending review)**, **Skipped (optional)**, **Confirm category**.

## Review, export and tracking
| Command | Purpose |
|---|---|
| `$RS package check JOB` | Review state plus approval blockers and warnings; re-validates the accepted resume and AI answers against the current profile |
| `$RS package approve JOB` | Approve after the user's explicit approval (never marks Applied) |
| `$RS ats JOB [--proposal] [--pdf FILE] [--json]` | Read-only ATS preflight: current-source validation, structured skill coverage and optional local PDF text comparison |
| `$RS render JOB [--pdf] [--proposal] [--style F]` | Write `out/review.html` and `out/resume.html` (or `preview.html`); `--pdf` prints with local Chrome/Edge. Validated style JSON is saved per job for later renders; `{}` resets defaults |
| `$RS track JOB saved\|applied\|assessment\|interview\|rejected\|offer\|withdrawn [--note "..."]` | Update status; `applied` requires a current approved package and freezes a snapshot |
| `$RS note JOB "text"` | Add a tracking note |

Rendering revalidates the selected resume against current profile facts before changing existing export files. A changed source can require a corrected proposal before another export. Historical snapshots stay intact.

The review page shows named current sources, wording differences and fresh rule-check results for summaries, bullets and AI answers (accepted and replacement drafts separately). User/profile answers are not labelled as AI-validated. Missing sources and rule failures remain visible for non-selected drafts. Checks cannot establish meaning, attribution or real-world truth, and viewing the page never changes approval. An invalid resume's cards show the resume validation issues instead of passing badges.

Review state: **draft** (not approved), **approved**, **stale** (profile, job, evidence, overrides or validation policy changed after approval). A requirements review is required; an explicitly saved empty list is valid for a description with no requirements. Snapshots live in `~/.resuskill/jobs/JOB/snapshots/<time>/` and never change. A snapshot includes the resume PDF only if it was rendered (`render JOB --pdf`) from the approved resume and current profile; otherwise `package.json` records why it was left out.

## Environment
- `RESUSKILL_HOME`: data directory (default `~/.resuskill`).
- `RESUSKILL_BROWSER`: path to a Chromium-based browser for `--pdf`.

PDF failures report launch errors, exit status or timeout and a bounded diagnosis without printing raw browser logs. Previous PDFs and provenance remain intact. The generated HTML is retained for manual Print → Save as PDF. If the host restricts browser launching, follow that host's permissions flow; do not disable browser sandbox protections.

## Export several tailored resumes

```bash
python3 "$SKILL/scripts/resuskill.py" batch-export JOB1 JOB2 --output /path/to/new-pack --pdf --json
```

Default: pending proposals. Use `--accepted` to select accepted resumes instead. All selected resumes are revalidated against current facts before a new output directory is created. Missing/invalid selections fail the whole preflight. Duplicate IDs and existing output directories are refused. `--style F` changes this pack only; otherwise each job's saved style is used.

The pack contains `index.html`, `report.json`, per-job resume/review HTML, successful PDFs, and `resumes.zip`. PDF failures return exit 1 and remain in the report; HTML is still available. Retry into a new directory. Other filesystem failures can leave an incomplete directory; do not deliver it as complete. No drafts are accepted, packages approved, applications submitted or tracking statuses changed. The pack contains personal resume content and evidence reviews; share only the intended resume files with employers.

## ATS preflight

```bash
python3 "<skill-dir>/scripts/resuskill.py" ats JOB --proposal --pdf /path/to/resume.pdf --json
```

Checks the accepted resume by default; `--proposal` explicitly selects the pending draft. Revalidates current facts before reporting. It reads stored data and the supplied PDF without changing drafts, approvals, tracking, or profile facts. Redirect JSON to a report file if needed; it includes resume content and source IDs, so treat it as personal data.

Skill coverage uses structured `skill` criteria from the reviewed requirements. Required, preferred and unspecified groups have separate counts; `any` groups need one alternative, `all` groups need each term. Matching uses ResuSkill's aliases and term boundaries. Presence in selected visible content counts; hidden hrefs, citations and unselected projects do not. Counts are keyword coverage, not eligibility or an ATS score. No groups means no assessed coverage, not a perfect match. Other technologies mentioned in the description are context only: they may be examples, negations or company boilerplate. Keep degree, experience, location and soft-skill judgments in the checklist.

A missing term is `supported_omitted`, `not_confirmed`, or `confirmed_absent`. Only the first suggests considering the existing skill, with profile source IDs. Confirm relevance and cite the actual project facts before rewriting bullets; never add unconfirmed skills to chase keywords. The checker does not rewrite or accept resumes automatically.

`--pdf FILE` checks the actual export, using local Poppler `pdftotext` or optional Python `pypdf`. Without either parser, PDF checks remain `not_checked` with setup guidance; HTML/content checks still run. Files must have a PDF header and be at most 20 MiB; the pypdf fallback rejects encrypted files and files over 30 pages. It compares contact fields, headings, summary, entry labels, dates, bullets, education labels, certificate names and skills with the selected current content, tolerating whitespace/typography differences. Missing text, clipping or stale/different exports produce errors. It does not authenticate file provenance, verify exact visual layout, compare every profile field, or emulate a particular employer's parser. Inspect page images and the employer's autofilled fields yourself.

Exit 1 on rejected input/current-claim validation or PDF text errors. Warnings, uncovered keyword groups and unavailable optional parsers return 0 and remain visible in the report. No ATS service is contacted and no hiring outcome is predicted. The parsing guidance follows [Greenhouse's documented failure examples](https://support.greenhouse.io/hc/en-us/articles/200989175-Unsuccessful-resume-parse); different systems may behave differently.

## Outcomes and recurring gaps

`$RS insights [--json]` reads all readable saved jobs and reports their latest recorded tracking states, plus recurring requirement gaps against the **current** profile. It does not calculate conversion rates or infer why an employer rejected an application. Counts include closed applications and are not a submission-time cohort.

Unknown evidence, confirmed missing skills, other mismatches, user overrides and changed evidence appear separately. Equivalent skill groups retain `any`/`all` semantics; required and preferred requirements remain separate. Recurrence counts distinct jobs, with each requirement ID and its basis available for review. Jobs with no reviewed requirements and unusable records are disclosed. Missing profile leaves outcomes available without evaluating gaps; damaged records produce partial output and exit 1. The command changes no candidate records.

## Pipeline and next actions

`$RS pipeline [--json] [--output NEW_DIR]` shows every readable job's recorded application status, current package review state, listing observation and deadline, checklist counts, package blockers, pending drafts and a suggested next action. Unreadable records remain visible with repair guidance; partial results exit 1. An absent profile leaves package checks explicitly unevaluated.

Actions prioritize damaged data, closed/expired or unverified listings, package blockers, pending drafts and stale approvals. Applied, assessment and interview states suggest checking correspondence and recording progress; they never suggest submitting again. Offers and terminal outcomes have separate actions. These are advisory next steps, not scheduled reminders or automatic follow-ups.

`--output NEW_DIR` creates `index.html` and `report.json` in a new directory; existing directories are refused. The HTML is a local snapshot, with listing sources and expandable fit warnings. Regenerate it after changes. The command does not accept drafts, approve packages, change tracking, contact employers or alter submitted snapshots. Package checks reflect the current profile, not the frozen submitted package.

## Manual follow-ups

`followup set JOB --date YYYY-MM-DD [--note TEXT] [--id fN]` creates an active follow-up or explicitly reschedules/reactivates an unfinished one. `followup list JOB --json` shows overdue/due-today/upcoming using the local calendar. `followup complete JOB fN` and `followup cancel JOB fN` preserve history; repeating the same completion is harmless. Completed/cancelled entries cannot be reopened. Rejected, withdrawn and offer statuses inactivate reminders; reopening a job does not reactivate them without an explicit set. No notifications or employer messages are sent.

CLI operations on the candidate directory take an exclusive `.command-lock`. A conflicting command refuses without changing records. If a command crashed, first verify no command is still running before manually removing that lock directory. Locks are never automatically reclaimed. Internal Python functions are not a public concurrency interface; use the CLI for writes.
