#!/usr/bin/env bash
# UV Tool - Easy access to uvtool.py
# This passes all arguments to uvtool.py

# Ensure we're in the project root directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Find Python executable (prefer python3)
PYTHON_EXE=$(which python3 2>/dev/null || which python 2>/dev/null)

if [ -z "$PYTHON_EXE" ]; then
    echo "Error: Python not found in PATH"
    exit 1
fi

# Activate virtual environment if it exists but isn't activated
if [ -f .venv/bin/activate ] && [ -z "$VIRTUAL_ENV" ]; then
    source .venv/bin/activate
fi

# Run uvtool with all arguments
"$PYTHON_EXE" scripts/uvtool.py "$@" 