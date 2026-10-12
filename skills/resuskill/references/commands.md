# ResuSkill CLI reference

`$RS` below means `python3 "<skill-dir>/scripts/resuskill.py"`; expand it as that command, not a shell string variable. Add `--json` to most read commands for machine-readable output. Commands exit `0` on success, `1` on rejection or a blocked package check, and `2` for invalid command syntax. JSON validation errors include field paths and do not replace existing data. `package check --json` emits blockers on stdout with exit code 1; other rejected commands print `error:` on stderr.

## Overview
| Command | Purpose |
|---|---|
| `$RS status` | Data directory, profile revision, job count, PDF browser |
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
| `$RS job requirements JOB --file F` | Save the reviewed requirement list (all-or-nothing; excerpts must be verbatim) |
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
| `$RS render JOB [--pdf] [--proposal]` | Write `out/review.html` and `out/resume.html` (or `preview.html`); `--pdf` prints with local Chrome/Edge |
| `$RS track JOB saved\|applied\|assessment\|interview\|rejected\|offer\|withdrawn [--note "..."]` | Update status; `applied` requires a current approved package and freezes a snapshot |
| `$RS note JOB "text"` | Add a tracking note |

Review state: **draft** (not approved), **approved**, **stale** (profile, job, evidence, overrides or validation policy changed after approval). A requirements review is required; an explicitly saved empty list is valid for a description with no requirements. Snapshots live in `~/.resuskill/jobs/JOB/snapshots/<time>/` and never change. A snapshot includes the resume PDF only if it was rendered (`render JOB --pdf`) from the approved resume and current profile; otherwise `package.json` records why it was left out.

## Environment
- `RESUSKILL_HOME`: data directory (default `~/.resuskill`).
- `RESUSKILL_BROWSER`: path to a Chromium-based browser for `--pdf`.
