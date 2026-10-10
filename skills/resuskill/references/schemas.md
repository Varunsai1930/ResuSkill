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
| `availability` | `start_by` and/or `start_from` (dates) |
| `years_experience` | `years` (number), `area` (text). Always Unknown until evidence is confirmed |

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

## Stored data compatibility

This release retains schema version 1. Existing v1 profiles and jobs remain readable. Unsupported schema versions are refused before writes; never relabel a newer file as v1. Back up the data directory before upgrading. Future schema changes need explicit, tested migrations that preserve originals. Approvals from older validation policies become stale and require review; legacy evidence/overrides may also require reconfirmation.
