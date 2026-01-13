#!/usr/bin/env bash
# install.sh - create venv and install requirements for DupPicCheck
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_CMD="${PYTHON:-python3}"
VENV="$DIR/venv"
REQ="$DIR/requirements.txt"

echo "Using python: $PYTHON_CMD"

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "Python not found: $PYTHON_CMD" >&2
  exit 1
fi

if [ ! -f "$REQ" ]; then
  echo "requirements.txt not found in $DIR" >&2
  exit 1
fi

if [ ! -d "$VENV" ]; then
  echo "Creating virtualenv in $VENV"
  "$PYTHON_CMD" -m venv "$VENV"
else
  echo "Virtualenv already exists at $VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "Upgrading pip and installing requirements..."
python -m pip install --upgrade pip wheel
pip install -r "$REQ"

cat <<EOF
Setup complete!
Activate the environment with:
  source "$VENV/bin/activate"
Then run:
  ./DuPiCheck.sh --help
EOF
