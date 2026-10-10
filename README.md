# ResuSkill

An agent skill for **Claude Code** and **Codex** that turns your confirmed profile and a pasted job description into an evidence checklist, a tailored resume, reviewed answers and an application record. Deterministic checks reject detectable unsupported claims; you review the meaning before approval.

```text
Create profile → Add job → Review requirements → Tailor resume
→ Draft answers → Review & approve → Export PDF → Submit yourself → Track
```

Your coding agent does the writing. A small bundled Python CLI does the enforcing. You review everything and click Submit on the employer's site yourself.

> **Better applications > more applications.**

## Why it's trustworthy

A skill is instructions an agent follows, so ResuSkill pairs its workflow with executable checks:

| The agent | The CLI |
|---|---|
| Talks to you, reads your resume, drafts content | Stores your profile, jobs and packages under `~/.resuskill/` |
| Extracts job requirements | Rejects any requirement whose quote isn't really in the job description |
| Rewrites bullets for the job | Rejects bullets with numbers, years, technologies or credentials their sources don't contain |
| Drafts answers to allow-listed writing prompts | Fills exact factual fields from your profile; leaves sensitive and unclear questions to you |
| Explains results | Computes a deterministic **Met / Unmet / Unknown** checklist (no fake scores) |
| | Tracks Draft / Approved / Stale, and freezes exactly what you submitted |

Missing information stays **Unknown** in the checklist. The CLI checks citations and selected claim types; it cannot prove that a paraphrase is true or authenticate whether an agent actually obtained your approval.

## Example

```text
You:    Here's the job description for Demo Corp's backend internship. How do I match?
Agent:  Met 5 · Unmet 1 · Unknown 1
        ✓ Python and SQL: profile lists both
        ✓ Pursuing a CS bachelor's: B.S. Computer Science, Example State University
        ✓ REST APIs: you confirmed your Sample Analytics API bullet as evidence
        ✗ Rust (preferred): you said you don't have it
        ? Java or Kafka (preferred): not in your profile. Have you used either?

You:    Tailor my resume for it.
Agent:  [writes a proposal → CLI rejects "Built Java pipelines…": Java isn't in that bullet's sources]
        Here's a revised version; open review.html to compare each line with the original.
```

## Install

**Requirements:** Python 3.9+ available as `python3`. Check with `python3 --version`; install Python if it is absent. No Python packages are required. On Windows, run the installer in Git Bash/WSL or use the manual copy option below; use `python` if that is your Python command.

```bash
git clone https://github.com/Varunsai1930/ResuSkill.git
```

```bash
cd ResuSkill && ./install.sh
```

`install.sh` symlinks `skills/resuskill` into `~/.claude/skills/` and `~/.codex/skills/`. Use `./install.sh claude` or `./install.sh codex` for one tool, or add `--copy` to copy instead of symlinking. Restart the agent afterwards.

**Claude Code plugin (alternative):** inside Claude Code run `/plugin marketplace add Varunsai1930/ResuSkill`, then `/plugin install resuskill@resuskill`.

**Manual:** copy the `skills/resuskill` folder into your agent's skills directory.

## Try fictional data first

```bash
python3 skills/resuskill/scripts/resuskill.py demo --json
```

Open the returned `review` and `resume` paths. The demo creates a separate temporary data directory and leaves your real profile untouched. The fictional package stays a draft, with a salary question deliberately awaiting an answer or explicit skip. To continue it, set `RESUSKILL_HOME` to the returned `data_dir` for your commands. Run `package check JOB`, resolve the question, review the files, and approve only when ready. `--output NEW_DIR` keeps the demo in a new directory you choose; existing directories are refused.

## Use it

Just ask in plain language:

- "Use resuskill to set up my profile from this resume." (attach or point to the file)
- "Add this job and show me how I match." (paste the description)
- "Tailor my resume for the Demo Corp job."
- "Here are the application questions: …"
- "Check the package and export the PDF."
- "I submitted it. Mark it applied." / "Show my applications."

The agent asks before it changes your profile, shows you every rewritten line beside its original, and never answers sensitive questions (demographics, disability, veteran status, criminal history, salary, legal declarations) for you.

## What gets produced

For each job, under `~/.resuskill/jobs/<job-id>/out/`:

- `review.html`: checklist with evidence, original-vs-proposed bullets, every answer and its label.
- `resume.html`: single-column A4 resume; names, employers, dates and degrees always come from your profile.
- `<Your_Name>_Resume.pdf`: printed with your local Chrome/Edge (or use Print → Save as PDF).
- `snapshots/<time>/`: a frozen copy of what you submitted, unaffected by later profile edits.

## Privacy

- All data stays on your machine in `~/.resuskill/` (override with `RESUSKILL_HOME`). It's plain JSON you can read, back up or delete.
- Your agent sends what it reads, including your profile, to its model provider (Anthropic or OpenAI) as part of normal use, under your account's terms. Leave anything confidential out of the profile.
- Nothing is uploaded anywhere else. The skill makes no network requests.

## Limits

- Automated checks catch invented numbers, technologies and credentials; they can't judge meaning. Your review is what makes the content accurate.
- It does not find jobs, fill employer forms or submit applications.
- One profile, one resume template, English-oriented keyword rules.
- Unknown questions default to user input. The conservative writing-prompt allow-list may send harmless questions to you too.
- Cross-client behavioral evaluation is still required before claiming a validated public release. The [25-case evaluation pack](evals/README.md) records this separately from Python test results.

## Updating

Back up `~/.resuskill/` (or your `RESUSKILL_HOME`) before updating. Schema v1 remains readable; unknown versions are refused without overwriting them. Older approvals become stale when validation rules change. Review affected packages and reconfirm changed evidence before approving again. See [CHANGELOG.md](CHANGELOG.md).

## Development

```bash
python3 -m unittest discover -s tests
```

The CLI is `skills/resuskill/scripts/resuskill.py` (`--help` lists every command). See [PLAN.md](PLAN.md) for the design and [skills/resuskill/references](skills/resuskill/references) for the command and JSON references. A companion web app with the same workflow lives at [ResuApply](https://github.com/Varunsai1930/ResuApply).

For release qualification, run the CI OS/Python matrix, copied-install smoke test and both client evaluations. Tag a version and publish its changelog only after reviewing those results. This checkout's unreleased changes are not a published GitHub release.

## License

[MIT](LICENSE)
