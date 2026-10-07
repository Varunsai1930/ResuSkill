# ResuSkill CLI reference

`RS="python3 <skill-dir>/scripts/resuskill.py"`. Add `--json` to most commands for machine-readable output. Commands exit `0` on success and `1` with `error:` lines on stderr when input is rejected; rejected input is never partially saved.

## Overview
| Command | Purpose |
|---|---|
| `$RS status` | Data directory, profile revision, job count, PDF browser |
| `$RS jobs` | Tracker table: review state, status, checklist counts |

## Profile
| Command | Purpose |
|---|---|
| `$RS profile template` | Print the profile skeleton |
| `$RS profile show [--json]` | Show the profile with entry and bullet IDs |
| `$RS profile diff --file F` | Validate and list changes **without saving** |
| `$RS profile save --file F` | Validate, keep IDs, bump revision, archive old version (only after user confirms) |

## Jobs and checklist
| Command | Purpose |
|---|---|
| `$RS job add --company C --title T --description-file F [--location L] [--url U]` | Save a job description (`F` may be `-`) |
| `$RS job show JOB [--description]` | Job details, requirements, questions; `--description` prints the full text |
| `$RS job requirements JOB --file F` | Save the reviewed requirement list (all-or-nothing; excerpts must be verbatim) |
| `$RS checklist JOB` | Deterministic Met / Unmet / Unknown with basis and evidence |
| `$RS evidence link JOB REQ SOURCE...` | Record user-confirmed evidence (entry or bullet IDs) |
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
| `$RS questions categorize JOB QID factual\|sensitive_factual\|sensitive\|open` | Set the category the user chose; a question detected as sensitive can only stay sensitive |
| `$RS questions remove JOB QID` | Remove a question |
| `$RS answers propose JOB --file F [--model NAME]` | Store AI drafts for **open** questions (validated, pending review) |
| `$RS answers accept JOB [QID...]` | Accept pending drafts (all when no IDs) |
| `$RS answers set JOB QID --text "..." \| --file F \| --skip` | Store the user's own answer, or skip an optional question |
| `$RS answers confirm JOB QID` | User confirms the profile value (factual / sensitive_factual) |
| `$RS bank save JOB QID` | Save a non-sensitive accepted answer for reuse |
| `$RS bank list` | List saved answers |

Answer labels: **From profile**, **AI draft**, **User answer**, **Missing information**, **User input required**, **AI draft (pending review)**, **Skipped (optional)**, **Confirm category**.

## Review, export and tracking
| Command | Purpose |
|---|---|
| `$RS package check JOB` | Review state plus approval blockers and warnings |
| `$RS package approve JOB` | Approve after the user's explicit approval (never marks Applied) |
| `$RS render JOB [--pdf] [--proposal]` | Write `out/review.html` and `out/resume.html` (or `preview.html`); `--pdf` prints with local Chrome/Edge |
| `$RS track JOB saved\|applied\|assessment\|interview\|rejected\|offer\|withdrawn [--note "..."]` | Update status; `applied` requires a current approved package and freezes a snapshot |
| `$RS note JOB "text"` | Add a tracking note |

Review state: **draft** (not approved), **approved**, **stale** (profile or job changed after approval). Snapshots live in `~/.resuskill/jobs/JOB/snapshots/<time>/` and never change. A snapshot includes the resume PDF only if it was rendered (`render JOB --pdf`) from the approved resume and current profile; otherwise `package.json` records why it was left out.

## Environment
- `RESUSKILL_HOME`: data directory (default `~/.resuskill`).
- `RESUSKILL_BROWSER`: path to a Chromium-based browser for `--pdf`.
