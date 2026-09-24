"""Chalk — CLI entry point.

Commands: init, add, extract, rollover, export, generate, status (PRD
section 6.6). All logic lives in chalk.cli; run `python toolkit.py -h`.
"""

import sys

from chalk.cli import main

if __name__ == "__main__":
    # Preview output uses ✓/⚠/→ — emit UTF-8 even when piped on Windows,
    # where redirected output otherwise defaults to the legacy code page.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
