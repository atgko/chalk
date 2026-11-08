#!/usr/bin/env bash
# Double-click (macOS) or run (Linux) to start Chalk.
# The first run sets everything up (a minute or two).
cd "$(dirname "$0")" || exit 1

# A release download carries its own Python, packages already installed.
if [ -x python/bin/python3 ]; then
    if [ "$(uname)" = Darwin ]; then
        # The Apple-silicon and Intel downloads look the same once unzipped.
        # Catch the wrong one here instead of macOS's "Bad CPU type" error.
        # (An Intel download still runs on Apple silicon if Rosetta is installed.)
        bundle_arch=$(cat python/.chalk-arch 2>/dev/null)
        if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ]; then mac=apple; else mac=intel; fi
        wrong=""
        if [ "$bundle_arch" = arm64 ] && [ "$mac" = intel ]; then
            wrong="This copy of Chalk is for Macs with Apple silicon (M1 or later), but this Mac has an Intel processor.
Download the file ending in macos-x64.zip instead."
        elif [ "$bundle_arch" = x86_64 ] && [ "$mac" = apple ] && ! /usr/bin/arch -x86_64 /usr/bin/true 2>/dev/null; then
            wrong="This copy of Chalk is for Intel Macs, but this Mac has Apple silicon (M1 or later).
Download the file ending in macos-arm64.zip instead."
        fi
        if [ -n "$wrong" ]; then
            echo "$wrong"
            read -r -p "Press Enter to close."
            exit 1
        fi
        # macOS marks everything unzipped from a download as quarantined and
        # refuses to run the bundled Python, which isn't signed with an Apple
        # Developer ID. You approved this launcher (Privacy & Security > Open
        # Anyway), so lift the mark from Chalk's own python folder only.
        # Signing and notarizing the bundle would make this unnecessary
        # (see DECISIONS.md).
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
