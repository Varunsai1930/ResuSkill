# Milestone G verification

Baseline fc68174. Python 3.14.1, repository root.

PASS `python3 -m unittest discover -s tests -v`: 357 tests.
PASS `python3 tools/check_copy.py`; `git diff --check`.
Independent Code Reviewer ran 8 story tests with no confirmed actionable findings. It also independently ran the expanded copied-install smoke successfully. That smoke exercises migration, follow-ups, historical reporting, letters and stories through the actual copied CLI outside the checkout.

Coverage includes unknown results, contribution scope, pending replacements, unchanged application approval, changed sources, confirmed-evidence questions, disclosed skill overlap, corrupt data and staged export failures. cases-v7.json preserves the original 25 and adds 9 cases (34 per client). Behavioral/human review, remote matrix and visual checks remain release blockers. No lint/type/build commands configured.
