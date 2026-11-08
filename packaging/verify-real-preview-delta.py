#!/usr/bin/env python3
"""Regression proof that stdlib-only decode reconstructs real official release.

The caller downloads only the 227.1 installer and its genuine 247.1 patch,
not the full new installer. This validates production data on GitHub's runner.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clipmint.package_delta import apply_patch


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def verify(base: Path, patch: Path, manifest: Path, checksum: Path) -> None:
    info = json.loads(manifest.read_text())
    lines = checksum.read_text().strip().splitlines()
    if len(lines) != 1:
        raise ValueError("Invalid official checksum list")
    target_sha, filename = lines[0].split()
    if (not filename.endswith("_amd64.deb")
            or info["format"] != "tar-content-xz-v1"
            or info["base_version"] != "0.6.0~preview1.227.1"
            or info["target_version"] != "0.6.0~preview1.247.1"
            or info["patch_name"] != patch.name
            or info["base_sha256"] != sha256(base)
            or info["patch_sha256"] != sha256(patch)
            or info["patch_size"] != patch.stat().st_size
            or info["target_sha256"] != target_sha):
        raise ValueError("Release manifest or SHA256 verification failed")
    with tempfile.TemporaryDirectory(prefix="clipmint-release-regression-") as tmp:
        result = Path(tmp) / filename
        apply_patch(base, patch, result)
        if sha256(result) != target_sha:
            raise ValueError("Real patch failed byte-for-byte target reconstruction")
        fields = subprocess.run(
            ["/usr/bin/dpkg-deb", "-f", str(result),
             "Package", "Version", "Architecture"],
            text=True, check=True, capture_output=True,
        ).stdout
        for expected in (
            "Package: clipmint", "Version: 0.6.0~preview1.247.1",
            "Architecture: amd64",
        ):
            if expected not in fields:
                raise ValueError("Rebuilt archive Debian identity mismatch")
    print("Verified production 227.1 -> 247.1 patch with only stdlib decoder")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("Usage: verify-real-preview-delta.py BASE PATCH MANIFEST SHA256SUMS")
    verify(*(Path(argument) for argument in sys.argv[1:]))
