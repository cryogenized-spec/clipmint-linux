#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"

# Development launcher: never install packages or modify the machine.
# Prefer a developer-managed virtual environment, but also accept a Python
# interpreter with ClipMint's dependencies already installed.
if [[ -x .venv/bin/python ]]; then
  python=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
  python="$(command -v python3)"
else
  echo "Python 3 is required to run ClipMint from source." >&2
  exit 1
fi

if ! "$python" -c 'import PySide6, regex, nacl, keyring, secretstorage' >/dev/null 2>&1; then
  cat >&2 <<'EOF'
ClipMint source dependencies are not available to the selected Python.
For development, create a local virtual environment and install the pinned
requirements yourself:
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
Then run ./run.sh again.

For normal offline use, install ClipMint's prebuilt .deb instead.
EOF
  exit 1
fi

exec "$python" -m clipmint
