# Preserve HTML exports on interrupted writes

Baseline: e0cb650. Resume/review HTML and changed styling are staged before publication. Each destination is replaced atomically; a handled publication interruption rolls back previous files and removes newly created files. If rollback fails, backups remain at an explicit recovery path rather than being deleted. An uncatchable process kill may require manual recovery from the retained staging directory and command lock.

Failure injection covers a partial 40-character staging write, replacement errors, KeyboardInterrupt and persistent rollback errors. Existing validation preflight and HTML fallback remain in place.

PASS full Python suite: 387 tests; PASS copied-install smoke; PASS `git diff --check`. Independent Code Reviewer passed all 6 export-preflight tests and found no confirmed issues. No configured lint/type/build step.
