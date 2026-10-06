# ResuSkill — Implementation Plan

## 1. Goal

ResuSkill is an agent skill for **Claude Code** and **Codex**. It turns a verified candidate profile and a pasted job description into an evidence checklist, a tailored resume, reviewed answers and an application record. It follows the same workflow as the ResuApply web app, but the coding agent provides the language model and the chat interface.

```text
Create profile → Add job → Review requirements
→ Tailor resume → Draft answers → Review package
→ Render resume (HTML/PDF) → Submit manually → Track outcome
```

The user always submits the application themselves. The skill never fills or submits employer forms.

## 2. Core principle: the agent writes, scripts enforce

A skill is instructions, and an agent can ignore instructions. So every guarantee lives in a local Python CLI that ships with the skill:

| The agent (Claude / Codex) does | The scripts do |
|---|---|
| Talk to the user, gather facts | Store profile, jobs, packages and tracking data |
| Turn a resume or chat into proposed profile JSON | Validate the profile, assign stable IDs, keep revisions |
| Extract job requirements | Check that each quoted excerpt really appears in the job description |
| Propose evidence links and corrections | Calculate the Met / Unmet / Unknown checklist deterministically |
| Draft tailored bullets and answers | Reject invalid sources and new skills, numbers, dates or credentials |
| Explain results | Render the resume, track approval and staleness, freeze submitted snapshots |

The agent never edits stored data files directly. All writes go through the CLI, which validates every input.

## 3. Design decisions

- **Standard library only.** The CLI needs Python 3.10+ and nothing else, so installing the skill needs no `pip install`.
- **One portable skill folder.** `skills/resuskill/` uses the shared `SKILL.md` format. It works in Claude Code (`~/.claude/skills/`) and Codex (`~/.codex/skills/`). Codex UI metadata lives in `agents/openai.yaml`.
- **Local, readable storage.** Data lives in `~/.resuskill/` (override with `RESUSKILL_HOME`) as JSON files the user can read, back up or keep in git.
- **AI provider.** The user's own Claude or Codex session. Profile content is sent to that provider as part of normal agent use, so no separate anonymization step is needed. The README states this clearly.
- **One candidate, one fixed single-column resume template, manual tracking.**

## 4. Data layout

```text
~/.resuskill/
├── profile.json                 canonical profile (revisioned)
├── history/profile-r<N>.json    previous profile revisions
├── answer_bank.json             reusable approved answers
└── jobs/<job-id>/
    ├── job.json                 description, requirements, evidence, overrides,
    │                            questions, tracking status, notes, history
    ├── proposal.json            latest validated resume proposal
    ├── package.json             accepted resume, answers, approval state
    ├── snapshots/<time>/        frozen submitted packages
    └── out/                     resume.html, review.html, resume.pdf
```

**Profile:** contact details, links, education, experience, projects, skills, confirmed missing skills, certifications, preferences, availability and per-country work authorization. Every education, experience and project entry, and every bullet, has a stable ID. Missing facts stay missing. The agent never guesses them.

## 5. Workflow and rules

### Profile
- The agent gathers facts in chat or reads a resume file the user provides, then writes a proposed profile JSON.
- `profile diff` shows exactly what would change. The agent shows it to the user and runs `profile save` only after the user confirms.
- Saving keeps existing IDs, assigns new ones, increments the revision and archives the previous version.

### Job and requirements
- `job add` needs a company, a title and the description text. Location and URL are optional.
- The agent extracts structured requirements: text, category, importance (required / preferred / unspecified), a verbatim excerpt and an optional machine-checkable criterion.
- `job requirements` rejects the whole set if any excerpt is not found in the description, so nothing partial gets saved.
- The job description is treated as data. Instructions inside it are never followed.

### Checklist (deterministic)
- **Met:** confirmed profile evidence satisfies the requirement.
- **Unmet:** confirmed profile evidence conflicts with it.
- **Unknown:** information is missing, ambiguous or not comparable.
- Skills use case folding plus a small alias map. A skill missing from the profile is Unknown unless the user confirmed they lack it.
- Degree, graduation window, location / work mode, authorization and start date are compared only when the profile has that data.
- Experience and other requirements become Met only through **evidence links the user has confirmed** (requirement → profile entries or bullets). The agent may suggest links, and the user confirms them.
- Overrides need a recorded reason. Gaps stay visible but never block preparing an application.

### Resume tailoring
- The agent writes a proposal: which entries to include, in what order, rewritten bullets with `sources`, and skills to show.
- `resume propose` rejects it if:
  - a bullet cites unknown sources or sources from a different entry;
  - a bullet contains numbers or years not in its sources;
  - a bullet names technologies not in its sources or the entry's technology list;
  - a bullet adds credentials not in its sources (certified, degree, patent, award …);
  - listed skills are not in the profile.
- Names, employers, titles, dates, degrees and contact details always come from the profile, never from the proposal.
- Proposals are stored separately. Only `resume accept` changes the accepted resume, so regenerating never overwrites accepted work.
- Passing validation does not mean the text is correct. The review page shows the original and proposed text side by side for the user to check meaning.

### Questions and answers
- The user pastes the real questions, marking each as required or optional with an optional length limit.
- Rules sort each question into a category:
  - **factual:** answered from the profile;
  - **sensitive-factual:** authorization or sponsorship; filled from the profile, but needs explicit user confirmation;
  - **sensitive:** demographic, disability, veteran, criminal, salary or legal; user input required;
  - **open:** the agent drafts an answer with sources;
  - **unknown:** the user confirms the category first.
- Labels: **From profile**, **AI draft**, **Missing information**, **User input required**.
- AI drafts go through the same fabrication checks plus the length limit. Approved answers can be saved to the answer bank for reuse.

### Review, approval and tracking
- Review state: **Draft**, **Approved** or **Stale**. Tracking status: **Saved**, **Applied**, **Assessment**, **Interview**, **Rejected**, **Offer** or **Withdrawn**.
- Approval needs:
  - an accepted resume that still validates against the current profile;
  - an accepted answer for every required question;
  - every sensitive question resolved.
- Editing package content clears approval. A changed profile or job revision makes the package Stale.
- Approval never marks an application as Applied. Recording Applied requires a current approved package and freezes it, with the rendered files, as a snapshot. Later profile changes never alter it.

### Rendering
- `render` builds `resume.html` (A4 print styles, multi-page, no clipping) and `review.html`. The review page has the checklist, original vs proposed bullets and answers.
- `render --pdf` prints to PDF with a local Chrome, Chromium or Edge if one is found. Otherwise the user opens the HTML file and uses Save as PDF.

## 6. Repository layout

```text
ResuSkill/
├── .claude-plugin/              Claude Code plugin + marketplace manifests
├── skills/resuskill/
│   ├── SKILL.md                 workflow and rules for the agent
│   ├── agents/openai.yaml       Codex display metadata
│   ├── references/              CLI reference, JSON schemas, rules
│   ├── assets/                  resume template
│   └── scripts/
│       ├── resuskill.py         CLI entry point
│       └── resuskill_core/      storage, profile, jobs, checklist,
│                                validation, questions, package, render
├── tests/                       unittest suite with synthetic fixtures
├── install.sh                   symlinks the skill into Claude Code / Codex
├── README.md
└── PLAN.md
```

## 7. Milestones

| # | Deliverable | Acceptance gate |
|---|---|---|
| 1 | Storage, profile (template / diff / save / show), job add | Profile and jobs survive restarts. IDs stay stable across edits |
| 2 | Requirements validation, deterministic checklist, evidence links, overrides | Every result shows its evidence, and unknowns stay Unknown |
| 3 | Resume proposal validation, accept, render HTML/PDF, review page | A Python-only source never gains Java, new metrics or dates |
| 4 | Questions, answers, answer bank, approval, staleness, tracking, snapshots | A full package can be prepared, approved, marked Applied and retrieved unchanged after profile edits |
| 5 | SKILL.md, references, install script, plugin manifests, README, CI | The skill installs in Claude Code and Codex, and a synthetic end-to-end run passes |

## 8. Tests

The tests use `unittest` (no dependencies) with synthetic, non-identifying fixtures. They run in CI on Python 3.10–3.13. Required scenarios:

- Unsupported requirement excerpts are rejected, and nothing is saved.
- Missing information stays Unknown. Explicit conflicts show as Unmet.
- Invented technologies, metrics, years, credentials and cross-entry sources are rejected.
- Proposals never change the accepted resume until it is accepted.
- Profile edits keep IDs, increment the revision and make approved packages Stale.
- Approval is blocked by missing required or sensitive answers.
- Submitted snapshots stay unchanged after later edits.
- Rendering escapes HTML, so job or profile text cannot inject markup.

## 9. Out of scope

Form autofill, automatic submission, job discovery, numeric match scores, email tracking, multiple templates, DOCX export and cloud sync.
