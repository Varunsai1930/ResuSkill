# Windows CI encoding correction — 2026-10-24

Baseline: 7484544aa973c6eee24ea85588af078d500a8a7d.

GitHub run https://github.com/Varunsai1930/ResuSkill/actions/runs/40087818570 completed all nine configured jobs: six Linux/macOS jobs passed; all three Windows jobs failed. The Windows 3.11 log showed one decoding error and two failed multilingual assertions because tests read generated UTF-8 HTML using the default cp1252 decoder. Corrected the three test reads to explicit UTF-8; kept assertions and production output unchanged.

PASS `python3 -m unittest discover -s tests -v`: 379 tests, 18.232 seconds.
PASS `python3 tools/check_copy.py` and `git diff --check`.
Independent Code Reviewer passed the affected 23 tests and reviewed the three-line fix with no findings. It also reviewed d6f36b6..7484544 and ran 70 validation/checklist/profile/package tests with no confirmed release-blocking finding. At this local checkpoint, the actual Windows rerun was still required; the local result alone did not establish a Windows pass. The completed remote rerun is recorded below.

Logs retained outside temporary storage under `/Users/varun/.codex/visualizations/2026/10/21/01a15c6a-13e4-7322-8693-a0adb8de3e57/resuskill-eval-7484544/`. No lint/type/build commands are configured. Client behavioral evaluation and human/visual review remain separate release gates.

Follow-up: after the explicitly approved push of 4c53ecd, all nine CI jobs passed: https://github.com/Varunsai1930/ResuSkill/actions/runs/40119706013 . This confirms Windows execution of the correction on Python 3.9, 3.11 and 3.13.
