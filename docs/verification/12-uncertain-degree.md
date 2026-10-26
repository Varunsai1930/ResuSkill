# Uncertain degree claims

Baseline: fccff6f. A year/month spanning today was treated as a held degree by source generation even though the checklist returned Unknown. Missing graduation dates had the same problem. Sources now distinguish completion unknown from pursuing or completed, and the shared claim checks retain that distinction. Validation policy 15 makes existing approvals stale.

Regression cases cover absent/year/month dates, current-day and past completion, future dates and ongoing education through resume and answer validation. PASS `python3 -m unittest discover -s tests`: 382 tests. PASS `python3 tools/check_copy.py`. No configured lint, type-check or build step (standard-library Python). Independent review is recorded below.

Independent Code Reviewer confirmed and rechecked a mixed-degree parsing issue found during review; no remaining confirmed findings. Its final focused rerun passed all 26 validation tests. `git diff --check` passed.
