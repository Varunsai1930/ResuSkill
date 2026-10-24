# Windows CI encoding correction — 2026-10-24

Baseline: 7484544aa973c6eee24ea85588af078d500a8a7d.

GitHub run https://github.com/Varunsai1930/ResuSkill/actions/runs/40087818570 completed all nine configured jobs: six Linux/macOS jobs passed; all three Windows jobs failed. The Windows 3.11 log showed one decoding error and two failed multilingual assertions because tests read generated UTF-8 HTML using the default cp1252 decoder. Corrected the three test reads to explicit UTF-8; kept assertions and production output unchanged.

PASS `python3 -m unittest discover -s tests -v`: 379 tests, 18.232 seconds.
PASS `python3 tools/check_copy.py` and `git diff --check`.
Independent Code Reviewer passed the affected 23 tests and reviewed the three-line fix with no findings. It also reviewed d6f36b6..7484544 and ran 70 validation/checklist/profile/package tests with no confirmed release-blocking finding. Actual Windows rerun remains required; no claim that this local result is a Windows pass.

Logs retained outside temporary storage under `/Users/varun/.codex/visualizations/2026/10/21/01a15c6a-13e4-7322-8693-a0adb8de3e57/resuskill-eval-7484544/`. No lint/type/build commands are configured. Client behavioral evaluation and human/visual review remain separate release gates.
