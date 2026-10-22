# Edge-case register

Each row records a required invariant and its executable coverage or remaining gate. Unit tests are not behavioral evaluation results. Release status is in `status.md`.

| Risk | Required behavior | Coverage / status |
|---|---|---|
| Claim badges and stale sources | Current checks cannot establish semantic truth | test_claim_review; independent audit pending |
| Missing versus absent skill | Preserve Unknown, any/all and required/preferred | test_insights, test_checklist |
| Pipeline state | No repeat-submit suggestions; damaged data visible | test_pipeline |
| Copied installation | Run actual installed copy outside checkout, paths with spaces | tools/check_copy.py; added to nine CI jobs |
| Evaluation completeness | Missing cases, wrong manifest and incomplete human review cannot pass | test_eval_scoring, test_eval_runner; behavioral runs pending |
| Concurrent writes | Refuse a conflicting writer; never reclaim unexplained locks | test_followups; 6 focused cases passed, independent review completed |
| Follow-up lifecycle | Dates are explicit; terminal/reopened jobs cannot reactivate silently | test_followups; 6 focused cases passed, independent review completed |
| Historical reporting | Fixed submission evidence, honest denominators, chronology validation | test_history; 6 focused tests passed, independent recheck completed |
| Imports | Bound preview, explicit updates, idempotent resume after interruption | test_imports; 10 focused cases passed, independent recheck completed |
| Git evidence | Exact committed text; no repo execution; role/impact attested separately | test_ledger; 8 focused cases passed, independent recheck completed |
| Migration | New validated directory, original and snapshots unchanged | test_ledger; 8 focused cases passed, independent recheck completed |
| Cover letter | Optional artifact participates in current approval and snapshot | test_letters; 8 focused cases passed, independent recheck completed |
| Stories | Unknown results permitted; changed sources invalidate stories | Milestone G pending |
| HTML/PDF | Unicode, long inputs, escaping, failed export preserves prior files | Existing render tests; visual inspection pending |
| Agent meaning and permission | No invented facts, sensitive answers, or unseen-content approval | Both-client human-reviewed suite pending |

For each feature, add focused boundary and failure-injection tests, record actual commands and results, and retain any unavailable check as blocked/not run. No row establishes exhaustive coverage.
