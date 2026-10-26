# Tracking history recovery in job listings

Baseline: a813aa9. Job listing dates validate the history container and each event before dereferencing. Malformed entries become unreadable rows with recovery guidance; healthy jobs remain available. The jobs CLI returns exit 1 with partial text/JSON results. Reads do not repair or overwrite data. Empty/missing legacy history retains its existing creation-date display fallback; historical cohort rules remain separate.

Regression cases cover null, wrong containers, null/missing event fields, wrong timestamp/status types, healthy neighbors and legacy histories through the CLI.

PASS full suite: 389 tests; PASS copied-install smoke; PASS `git diff --check`. Independent Code Reviewer passed all 21 data-audit tests with no confirmed findings. No configured lint/type/build step.
