#!/usr/bin/env bash
# Normal users install the standalone .deb. Source-tree dependencies are
# installed only when a developer explicitly requests --dev.
set -euo pipefail

if [[ "${1:-}" == "--dev" && "$#" -eq 1 ]]; then
  cd -- "$(dirname -- "$0")"
  if ! python3 -m venv .venv; then
    echo "Could not create .venv; install python3-venv for your distribution." >&2
    exit 1
  fi
  .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
  echo "Developer environment ready. Start ClipMint with ./run.sh"
  exit 0
fi

if [[ "$#" -ne 0 ]]; then
  echo "Usage: ./install.sh [--dev]" >&2
  exit 2
fi

echo "ClipMint is distributed as a standalone .deb."
echo "Open https://github.com/cryogenized-spec/clipmint-linux/releases"
echo "Download the latest .deb release and double-click it in Nemo to install."
echo "A normal installation does not require developer Python dependencies."
