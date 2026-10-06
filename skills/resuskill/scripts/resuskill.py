#!/usr/bin/env python3
"""ResuSkill CLI entry point. Requires only the Python 3.9+ standard library."""

import sys
from pathlib import Path

if sys.version_info < (3, 9):
    sys.exit("ResuSkill needs Python 3.9 or newer.")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from resuskill_core.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
