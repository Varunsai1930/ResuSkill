# Missing saved-job records remain visible

Baseline: e30cd1e. A saved-job directory without a usable job.json now produces an unreadable-row error instead of disappearing. Listings, pipeline and historical reports retain the error and healthy neighbors; reads never create replacement facts.

Because missing records can also result from interrupted imports, recovery inventory permits only empty new-job directories named by the already-validated journal plan. Unrelated missing records, explicit null files and unexpected contents remain blocking errors. Regression cases cover missing/null records and recovery after an empty destination was created, with unrelated/nonempty folders rejected.

PASS full suite: 391 tests; PASS copied-install smoke; PASS `git diff --check`. Independent Code Reviewer passed 12 import tests and 22 data-audit tests with no confirmed findings. No configured lint/type/build step.
