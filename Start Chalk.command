#!/usr/bin/env bash
# Double-click (macOS) or run (Linux) to start Chalk.
# The first run sets everything up (a minute or two).
cd "$(dirname "$0")" || exit 1

if [ ! -x .venv/bin/python ]; then
    echo "Setting up Chalk for the first time..."
    PY=python3
    command -v python3 >/dev/null 2>&1 || PY=python
    if ! "$PY" -m venv .venv; then
        echo
        echo "Chalk needs Python 3.11 or newer. Install it from https://www.python.org/downloads/"
        echo "then start Chalk again."
        read -r -p "Press Enter to close."
        exit 1
    fi
fi

.venv/bin/python -m chalk.launcher "$@"
status=$?
if [ $status -ne 0 ]; then
    read -r -p "Press Enter to close."
fi
exit $status
