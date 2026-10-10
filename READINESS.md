# Public readiness review — 10 October 2026

Status: implementation hardening prepared for teammate testing; full public-release qualification remains open. This is not a versioned release. The earlier local review edits were preserved and extended.

## Bugs and gaps fixed

| Failure | Resulting behavior |
|---|---|
| Broad `what/how/describe` matching and category overrides permitted AI answers to unclear personal questions | Only specific complete writing prompts permit AI drafts. Unknown prompts accept the user's answer directly; category changes, old drafts and bank saves cannot bypass the rule. |
| Factual keywords could put the candidate's email into a manager-email answer, or a full name into a first-name field | Complete field-label matching; ambiguous and partial fields require user input. Negated sponsorship/authorization prompts do not get an inverted profile answer. |
| Unknown lowercase countries could inherit another country's authorization | Match the complete country clause; unknown or compound places remain unanswered. |
| Old stored field mappings survived stricter classification | Recheck mappings before resolving or confirming profile answers; older approvals become stale. |
| Malformed nested JSON could throw uncaught exceptions or silently coerce values | Shape validation at profile, requirement, resume and answer boundaries; field-path errors, strict booleans, duplicate-key and non-finite-number rejection. |
| AI answers could omit sources or implicitly borrow the entire profile summary | Require explicit supporting citations; expose skill source IDs; limit claim checks to cited sources and their technologies. Resume bullets must cite bullet IDs. |
| Accepted AI answers could outlive their evidence | Revalidate during package checks; recheck current policy and blockers when recording an application snapshot. |
| Changed evidence still counted as confirmed; partial surviving links could retain “Met” | Record source hashes, require the complete confirmed set to remain current, and expire overrides on profile change. Evidence/override changes invalidate approval. |
| Requirements review could be silently skipped; blocked checks returned success | Require a saved review, including an explicit empty review when appropriate. Blocked `package check` returns 1, including JSON mode. |
| Automatic factual values could exceed form limits | Check every resolved answer's length; reject zero/negative question limits. |
| Duplicate draft IDs overwrote each other; duplicate accept IDs could crash | Reject duplicate proposals and deduplicate acceptance IDs. |
| Replacement answer drafts were hidden behind accepted answers | Show both texts and their sources in review HTML. Pending resume warnings compare content rather than timestamps. |
| Initial profile diff hid new bullet text | Show imported entry fields and every bullet before confirmation. |
| Invalid calendar days were accepted; month-end comparisons used day 31 for every month | Validate real dates and compare partial dates using actual month ends. |
| Sponsorship availability was treated as proof of eligibility | Return Unknown until eligibility has supporting information. |
| Input metadata counters, duplicate authorization countries and duplicate certification IDs could corrupt identity/lookup assumptions | Ignore incoming counters; validate duplicate records and IDs. Refuse unsupported stored schema versions before writes. |
| Installer could report success despite missing Python or conflicting installs | Check the runtime before installation; return failure for conflicts; exclude bytecode caches from copies. |

## Additions

- `demo` creates a fictional draft, review HTML and resume HTML in a fresh directory. It leaves real data untouched and demonstrates a required user decision before approval.
- `evals/` contains 25 synthetic agent scenarios and a human-reviewed result scorer. It covers unsupported claims, personal questions, prompt injection, checklist judgments and skipped workflow steps. It is not evidence of completed client runs.
- Updated skill instructions include an advisory semantic review of ownership, leadership, scale, causality and outcomes before presenting drafts. The CLI remains responsible for deterministic checks; no extra provider API is required.
- Added changelog, feedback issue template, compatibility guidance and release qualification instructions.

## Verification completed

- `python3 -m unittest discover -s tests`: **100 tests passed**, up from the 69-test baseline, on macOS with Python **3.14.1**.
- Exercised **1,764 malformed-input mutations** across the four JSON input boundaries in temporary storage: **zero uncaught exceptions**. This checks crash handling, not universal semantic correctness.
- Copied installation and demo executed from a path containing spaces; existing destination correctly refused and real profile unchanged.
- Skill frontmatter validator passed; `git diff --check` passed.
- Generated demo HTML and checked content, including accepted/replacement answers and source text. Existing PDF snapshot tests exercise current/stale PDF inclusion with test PDFs.
- Used the code graph for discovery and checked current source before edits. Graph coverage reported no recorded gaps for the changed source files; excluded bytecode caches were not used as evidence.

## Still required before a validated public release

1. Run and human-review all 25 agent scenarios in both Claude Code and Codex. No cross-client transcripts or model evaluation scores were collected in this session.
2. Run the repository's Python/OS CI matrix. Local results do not establish Windows/Linux or Python 3.9/3.11/3.13 runtime compatibility.
3. Check rendered HTML and a real browser-generated PDF visually. The in-app browser blocked the local `file:` preview URL, so visual verification was not completed and no workaround was attempted.
4. After reviewing those results, create a versioned release. The changelog remains Unreleased while teammates test the changes on `main`.

Lexical checks cannot prove semantic truth, guarantee complete requirement extraction, catch every technology, or authenticate whether the agent obtained a real user's approval. Agent behavior still needs evaluation and human review. There is no supported claim of zero bugs or zero hallucinations.
