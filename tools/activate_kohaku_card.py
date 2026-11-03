#!/usr/bin/env python3
"""Install the exact approved Kohaku card locally and/or publish it to PR #11.

Usage:
    python3 tools/activate_kohaku_card.py ~/Downloads/kohaku_card.png --install-local
    python3 tools/activate_kohaku_card.py ~/Downloads/kohaku_card.png --install-local --publish-pr

No package reinstall or alteration of existing clipboard history is required
for --install-local. --publish-pr uses your existing GitHub CLI login.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

EXPECTED_SHA256 = "585800ce776353d84a9d60e798ff591d06b580f95be0943a46ae67c1c107817a"
EXPECTED_SIZE = 2_341_345
EXPECTED_DIMENSIONS = (941, 1672)
GITHUB_PATH = "repos/cryogenized-spec/clipmint-linux/contents/clipmint/assets/kohaku_card.png"
GITHUB_BRANCH = "feat/kohaku-card-canonical-asset"


def check_artwork(path: Path) -> bytes:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != EXPECTED_SIZE or digest != EXPECTED_SHA256:
        raise ValueError(
            "This is not the approved Kohaku card. Please use the original "
            "941x1672 PNG without cropping, recompression, or edits. "
            f"SHA256 received: {digest}"
        )
    if not raw.startswith(b"\\x89PNG\\r\\n\\x1a\\n") or len(raw) < 26:
        raise ValueError("Approved card is not a valid PNG")
    dimensions = struct.unpack(">II", raw[16:24])
    if dimensions != EXPECTED_DIMENSIONS:
        raise ValueError(f"Unexpected PNG dimensions: {dimensions}")
    print("PASS: Original approved artwork verified (SHA-256, file size, PNG dimensions).")
    return raw


def install_local(raw: bytes) -> Path:
    data_root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    directory = data_root / "clipmint"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "kohaku_card.png"
    # Atomic file swap: do not touch the user's history database or vault.
    with tempfile.NamedTemporaryFile(prefix=".kohaku-", suffix=".png", dir=directory, delete=False) as f:
        temporary = Path(f.name)
        f.write(raw)
    try:
        temporary.chmod(0o644)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Installed card: {target}")
    print("Quit ClipMint fully from the system tray and reopen it to load the card.")
    return target


def publish_to_pr(raw: bytes) -> None:
    if shutil.which("gh") is None:
        raise RuntimeError("GitHub CLI missing. Install with: sudo apt install gh")
    status = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if status.returncode:
        raise RuntimeError("GitHub not authenticated. Run: gh auth login --web")
    request = {
        "message": "art(kohaku): add exact approved full-body character card",
        "content": base64.b64encode(raw).decode("ascii"),
        "branch": GITHUB_BRANCH,
    }
    # Stream ~3MB JSON through stdin; shell argument size limits do not apply.
    result = subprocess.run(
        ["gh", "api", "-X", "PUT", GITHUB_PATH, "--input", "-"],
        input=json.dumps(request).encode("utf-8"),
        capture_output=True,
        timeout=180,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace")[:900]
        raise RuntimeError("GitHub upload failed: " + message)
    response = json.loads(result.stdout)
    actual = response.get("content", {}).get("sha", "")
    if actual != "c891a6c9e76f355802bb11e43056240d141427ca":
        raise RuntimeError("GitHub reported an unexpected content blob SHA: " + actual)
    print("PASS: Exact Kohaku image committed to PR #11.")
    print("https://github.com/cryogenized-spec/clipmint-linux/pull/11")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("png", type=Path, help="Path to the original Kohaku card PNG")
    parser.add_argument("--install-local", action="store_true",
                        help="Activate the artwork in the existing installed ClipMint app")
    parser.add_argument("--publish-pr", action="store_true",
                        help="Commit the exact image to the public GitHub PR branch")
    args = parser.parse_args()
    if not args.install_local and not args.publish_pr:
        parser.error("Specify --install-local and/or --publish-pr")
    try:
        raw = check_artwork(args.png.expanduser())
        if args.install_local:
            install_local(raw)
        if args.publish_pr:
            publish_to_pr(raw)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
