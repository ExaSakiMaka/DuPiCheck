#!/usr/bin/env bash
# DuPiCheck.sh - activate venv and run main.py with passed arguments

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/venv"

# Parse launcher-only flags (consumed by this script): --install, --no-install
INSTALL=false
NO_INSTALL=false
ARGS=()
for a in "$@"; do
  case "$a" in
    --install) INSTALL=true ;;
    --no-install) NO_INSTALL=true ;;
    *) ARGS+=("$a") ;;
  esac
done

if [ -d "$VENV" ]; then
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
else
  # venv not found: try to create it using install.sh unless --no-install was passed
  if [ "$NO_INSTALL" = "true" ]; then
    echo "virtualenv not found at $VENV and --no-install specified; using system python"
  else
    if [ "$INSTALL" = "true" ]; then
      echo "Creating virtualenv via install.sh..."
      "$DIR/install.sh"
      # shellcheck disable=SC1091
      source "$VENV/bin/activate"
    else
      if [ -x "$DIR/install.sh" ]; then
        read -r -p "virtualenv not found. Create it now? [Y/n]: " yn
        yn=${yn:-Y}
        case "$yn" in
          [Yy]* )
            echo "Running install.sh..."
            "$DIR/install.sh"
            # shellcheck disable=SC1091
            source "$VENV/bin/activate"
            ;;
          * )
            echo "Proceeding with system python"
            ;;
        esac
      else
        echo "install.sh not found or not executable; proceeding with system python"
      fi
    fi
  fi
fi

exec python "$DIR/main.py" "${ARGS[@]:-}"
