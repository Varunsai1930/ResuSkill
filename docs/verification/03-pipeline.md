# Pipeline verification

Scope: read-only `pipeline` command and optional local HTML/JSON export; baseline ad54ebc.

Run from repository root with Python 3.14.1:

- PASS: `python3 -m unittest discover -s tests -p 'test_pipeline.py' -v` — 9 tests covering absent profiles, unverified/expired/future observations, approved/stale states, pending drafts, sensitive blockers, fit evidence, submitted/terminal statuses, corrupt records, escaping, read-only behavior and export overwrite refusal.
- PASS: `python3 -m unittest discover -s tests -v` — 308 tests.
- PASS: `python3 skills/resuskill/scripts/resuskill.py --help`.
- PASS: `RESUSKILL_HOME=/private/tmp/resuskill-verification/claim-demo python3 skills/resuskill/scripts/resuskill.py pipeline --output /private/tmp/resuskill-verification/pipeline-demo --json` — fictional job exported with listing recheck action, sensitive-answer blocker and confirmed preferred Rust gap.
- PASS: `git diff --check`.

Codebase Memory identified package validation, review-state calculation and listing assessment; affected paths had no recorded coverage gap, and current source was checked. Graph coverage is best effort.

Independent review remains unavailable after the Code Reviewer failed with an account usage limit. Self-review checked action precedence, incomplete-data disclosure, HTML escaping, validated listing links, current-profile semantics, existing-directory refusal and preservation of candidate records. No additional confirmed issue found within this scope.

BLOCKED: visual browser inspection. The browser tool rejected the local `file:` URL because its policy permits HTTP(S) only. No workaround was attempted. HTML generation, content and escaping passed automated checks; layout was not visually verified.

No configured lint, type-check or build command exists in this standard-library Python project. The cross-platform CI matrix was not run locally. This view is a snapshot with advisory actions; it has no due-date scheduler, automatic submission or employer messaging.
