# Milestone F verification

Baseline 1ce8de1. Python 3.14.1, repository root.

PASS `python3 -m unittest discover -s tests -v`: 349 tests.
PASS `python3 tools/check_copy.py`; `git diff --check`.
Independent Code Reviewer ran 8 letter tests. Found incomplete stored paragraphs/defaults could pass shape checks and crash rendering. Stored letters now require normalized complete content and valid required paragraph fields. Regression and independent recheck pass with no unresolved confirmed findings.

Coverage includes pending-versus-accepted content, approval lifecycle, retired evidence, changed profile, immutable submitted snapshots, failed snapshot cleanup, HTML escaping, failed PDF cleanup and resume-only compatibility. cases-v6.json adds letter review (33 total cases). Real client/human behavioral evaluation, remote matrix and visual review remain incomplete release gates. No lint/type/build commands configured.
