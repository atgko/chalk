#!/usr/bin/env bash
# Double-click (macOS) or run (Linux) to start Chalk.
# The first run sets everything up (a minute or two).
cd "$(dirname "$0")" || exit 1

# A release download carries its own Python, packages already installed.
if [ -x python/bin/python3 ]; then
    # macOS marks everything unzipped from a download as quarantined and
    # refuses to run the bundled Python, which isn't signed with an Apple
    # Developer ID. You approved this launcher (right-click > Open), so lift
    # the mark from Chalk's own python folder only. Signing and notarizing
    # the bundle would make this unnecessary (see DECISIONS.md).
    if [ "$(uname)" = Darwin ]; then
        xattr -dr com.apple.quarantine python 2>/dev/null
    fi
    # Use only the bundled packages, not ones installed elsewhere.
    unset PYTHONHOME PYTHONPATH
    export PYTHONNOUSERSITE=1
    python/bin/python3 -m chalk.launcher "$@"
    status=$?
    [ $status -ne 0 ] && read -r -p "Press Enter to close."
    exit $status
fi

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
