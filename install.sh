#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ "$(uname -s)" != Linux || "$XDG_SESSION_TYPE" != x11 ]]; then
  echo "ClipMint v0.1 requires Linux Mint with X11." >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y ffmpeg python3-venv libxcb-cursor0
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
echo "Installed. Run ./run.sh"
