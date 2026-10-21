# JSON shapes

Dates are real calendar dates in `YYYY`, `YYYY-MM` or `YYYY-MM-DD`; ongoing roles use `"present"`. Unknown optional values are `null` or empty, never guessed. Wrong JSON shapes, unknown fields and duplicate keys are rejected with field paths. Lists must contain the documented types; numeric `0`/`1` are not booleans.

## Profile (`profile diff/save`)

Start from `profile show --json` when editing so `id` fields are kept. New entries and bullets may omit `id`; the CLI assigns one. `_meta` is managed by the CLI and ignored on input.

```json
{
  "contact": {"name": "required", "email": "", "phone": "", "location": "City, ST",
              "links": {"linkedin": "", "github": "", "portfolio": ""}},
  "summary": "optional, the user's own words",
  "education": [{"id": "edu-1", "institution": "required", "degree": "B.S.", "field": "Computer Science",
                 "start": "2023-08", "end": "2027-05", "gpa": "3.7", "bullets": [{"id": "edu-1-b1", "text": "..."}]}],
  "experience": [{"id": "exp-1", "organization": "required", "title": "", "location": "",
                  "start": "2024-06", "end": "2024-08", "technologies": ["Python"],
                  "bullets": [{"id": "exp-1-b1", "text": "One confirmed accomplishment"}]}],
  "projects": [{"id": "proj-1", "name": "required", "role": "", "link": "", "start": "", "end": "",
                "technologies": [], "bullets": []}],
  "skills": [{"name": "Python", "category": "Languages"}],
  "skills_absent": ["Skills the user explicitly confirmed they do not have"],
  "certifications": [{"name": "", "issuer": "", "date": ""}],
  "preferences": {"roles": [], "locations": [], "work_mode": "remote | hybrid | onsite | any | null"},
  "availability": {"start_date": "2027-06", "notes": ""},
  "authorization": [{"country": "US", "authorized": true, "requires_sponsorship": false}]
}
```

Bullets may be plain strings on input. `authorized` / `requires_sponsorship` are `true`, `false` or `null` (unknown); each country appears once. Source IDs for citations: `summary`, entry IDs (`exp-1`), bullet IDs (`exp-1-b2`), certification IDs (`cert-1`), and explicit profile skills (`skill:python`, `skill:sql`, using the canonical lowercase skill name). Resume bullets must cite bullet IDs.

## Requirements (`job requirements`)

```json
[
  {"id": "r1", "text": "Python and SQL", "category": "skill", "importance": "required",
   "excerpt": "verbatim text copied from the description",
   "criterion": {"type": "skill", "skills": ["Python", "SQL"], "match": "all"}}
]
```

- `category`: `skill`, `education`, `experience`, `location`, `authorization`, `availability`, `other`.
- `id` may be omitted: a requirement with the same `text` and `excerpt` as a saved one keeps its id, and new ones get an id never used before. Evidence links and overrides survive a re-save only for requirements that did not change.
- `importance`: `required`, `preferred`, `unspecified`.
- `criterion` is `null` when the requirement is not explicitly comparable. Types:

| type | fields |
|---|---|
| `skill` | `skills` (list), `match`: `all` \| `any` |
| `degree` | `level`: `associate` \| `bachelor` \| `master` \| `phd`; `fields` (list, optional); `status`: `any` \| `completed` \| `pursuing` |
| `graduation_window` | `from`, `to` (dates; either may be omitted) |
| `location` | `locations` (list) and/or `work_mode`: `remote` \| `hybrid` \| `onsite` |
| `authorization` | `country` (ISO code, e.g. `US`), `sponsorship_available`: `true` \| `false` \| `null` |
| `availability` | `start_from` is the earliest job start; `start_by` is the latest acceptable start (dates). A profile date means available from that date: earlier availability is compatible. If only `start_from` is given, later candidate availability stays Unknown because no latest start is known. |
| `years_experience` | `years` (number), `area` (text). Always Unknown until evidence is confirmed |

## Listing observations (`job observe`)

Record what you actually read, separately from the application's Saved/Applied state. This command makes no network requests and cannot authenticate an agent's observation. Pass the complete object to replace an earlier observation; omitted fields become unknown/default, not inherited.

```json
{
  "status": "open",
  "verified_at": "2026-10-19T12:00:00+05:30",
  "source_url": "https://example.com/careers/123",
  "status_excerpt": "Apply now",
  "deadline": "2026-10-24",
  "program_start": null,
  "program_end": null,
  "intake_note": "Summer intake year is not stated",
  "eligibility": "conditional",
  "eligibility_note": "Requires relocation; willingness is unconfirmed"
}
```

- `status`: `unknown`, `open`, `closed`. Open/closed needs a timezone-aware `verified_at`, a public HTTP(S) `source_url` and a verbatim `status_excerpt` from the observed page. This excerpt may describe a newly closed page rather than the older saved job description.
- `deadline`: null, full `YYYY-MM-DD`, or a timezone-aware ISO timestamp when an exact cutoff is known. Date-only cutoffs include the whole local calendar day; their timezone is unspecified. Do not invent a timezone.
- `program_start`/`program_end`: null or full dates, in order. Ambiguous or yearless summer programs stay null with an `intake_note`.
- `eligibility`: `unknown`, `preference_match`, `conditional`, `mismatch`. This records a reviewed assessment, not guaranteed eligibility. Conditional/mismatch requires a note. A skills match cannot override location, graduation or availability conditions.
- Missing metadata on older jobs stays unverified. The tracker/review/check commands distinguish `observed_open`, `closed`, `expired`, `stale` (open observation older than seven days), and `unverified`. Future timestamps are flagged. Eligibility conditions and past program dates remain visible.
- Changes increment the job revision and make old approvals stale. Listing warnings do not prevent historical tracking or approval of content; they never imply permission to apply.

## Repositories (`job repos`)

A JSON list as returned by `https://api.github.com/users/<name>/repos`; extra GitHub fields are ignored. Used fields: `name` and `html_url` (required text), `description`, `language`, `pushed_at` (text or null), `topics` (list of text), `fork`, `archived`, `size`, `stargazers_count`. The agent may add `readme` (text) and `languages` (list of names, or GitHub's `{name: bytes}` object).

Language names must be non-empty text; byte counts, `size` and `stargazers_count` must be non-negative integers, and `fork`/`archived` must be booleans when supplied. Combine all fetched repository pages. Ranking uses metadata and README mentions as suggestions, not proof of technologies used; verify the code and confirm project facts before importing them.

## Resume proposal (`resume propose`)

```json
{
  "summary": {"text": "optional", "sources": ["summary", "exp-1-b1"]},
  "experience": [{"entry": "exp-1", "bullets": [{"text": "rewritten bullet", "sources": ["exp-1-b1"]}]}],
  "projects": [{"entry": "proj-1", "bullets": [{"text": "...", "sources": ["proj-1-b1", "proj-1-b2"]}]}],
  "education": ["edu-1"],
  "certifications": [],
  "skills": ["Python", "SQL"]
}
```

- Entries appear in the order given; omit an entry to leave it out. Omitting `education`, `certifications` or `skills` includes everything from the profile.
- Each bullet cites one or more bullet IDs **from the same entry**. Merging two source bullets into one is fine.
- Rejected when a bullet adds numbers, years, technologies or credentials that are not in its sources (technologies listed on the entry are allowed), or when a skill is not in the profile.
- Titles, employers, dates, degrees and contact details are rendered from the profile, so do not put them in bullets unless the source bullet has them.

## Answer drafts (`answers propose`)

```json
[
  {"question_id": "q3", "text": "Draft answer within the length limit", "sources": ["exp-1-b1"], "bank_id": "bank-2"}
]
```

Only **open**, allow-listed writing prompts accept drafts. Every draft needs non-empty text and at least one source. Numbers, technologies and credentials must come from those sources (including their entry technologies); the profile summary is not included implicitly. Cite `skill:python` to mention that explicit profile skill. Duplicate `question_id` values are rejected. `bank_id` is optional and records reuse, but a bank ID alone is not evidence.

## Resume presentation (`render --style F`)

Use a JSON object with any of these keys; omitted keys use defaults. See `assets/navy_style.json` for a complete example. Styles change presentation only; they cannot supply resume facts, arbitrary HTML/CSS, external assets or hide sections.

| Key | Allowed values |
|---|---|
| `font` | `sans` (default), `serif` |
| `font_size_pt` | 9–12; default 10.5 |
| `name_size_pt` | 16–30; default 19 |
| `line_height` | 1.1–1.6; default 1.38 |
| `margin_mm` | 8–25; default 15 |
| `section_gap_pt` | 4–16; default 9 |
| `accent`, `rule` | Six-digit hex colors such as `#193c5b` |
| `uppercase_name`, `link_labels`, `degree_first` | Boolean; default false |
| `projects_heading` | `Projects` or `Project Experience` |
| `skills_heading` | `Skills` or `Technical Skills` |
| `section_order` | A permutation of `summary`, `education`, `experience`, `projects`, `skills`, `certifications`; every key exactly once |

The settings are kept in the job's `out/style.json` and reused for both accepted and proposal renders. Pass `{}` to reset. PDF provenance includes non-default styling, so a PDF from an older style cannot be paired with a newer HTML snapshot. Existing snapshots remain unchanged. Uploaded PDF templates are visual references: the agent translates their supported design choices into this JSON, rather than importing PDF code or guaranteeing pixel-identical reproduction. Inspect the exported pages; content can span multiple pages and is never silently shortened to fit.

## Stored data compatibility

This release retains schema version 1. Existing v1 profiles and jobs remain readable. Unsupported schema versions are refused before writes; never relabel a newer file as v1. Back up the data directory before upgrading. Future schema changes need explicit, tested migrations that preserve originals. Approvals from older validation policies become stale and require review; legacy evidence/overrides may also require reconfirmation.

## Follow-ups

Optional `tracking.followups` records have stable `fN` IDs, full calendar `date`, `note`, `state` (`active`, `inactive`, `completed`, `cancelled`), `created_at` and `updated_at`. Legacy jobs without them use an empty list. The CLI manages IDs/timestamps. Follow-ups do not change job revision, package approval or submission snapshots. Offer/rejected/withdrawn transitions inactivate active records.

Historical reporting reads existing `tracking.applied_at`, ordered `tracking.history` events and the referenced immutable snapshot's checklist. It adds no stored fields and does not rewrite legacy data. Dates used for cohort filters retain the recorded timestamp's offset.
