# PDF snapshot integrity

Baseline: 8c41915. PDF provenance now includes a SHA-256 of the complete PDF file (render version 3). Snapshot preflight excludes altered, truncated and legacy unstamped files; a second check on copied bytes prevents recording submission when the PDF changes during copying. Previous immutable snapshots remain readable.

Regression coverage exercises valid current output, valid-but-replaced output, truncation, missing digest, stale resume/style and a changed copied PDF. The PDF test fixture now includes a final trailer so its synthetic print output satisfies the real completeness contract.

PASS `python3 -m unittest discover -s tests`: 384 tests; PASS `python3 tools/check_copy.py`; PASS `git diff --check`. Independent Code Reviewer found no confirmed issues and passed all 21 package tests. No configured lint/type/build steps.
