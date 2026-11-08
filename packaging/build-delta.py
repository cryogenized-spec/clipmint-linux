#!/usr/bin/env python3
"""Generate a verified optional ClipMint .deb delta in the GitHub publisher.

Both the full package and SHA256SUMS remain mandatory release assets.
Never publish a patch unless applying it reproduces the new .deb byte-for-byte.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import bsdiff4

# Executed as python packaging/build-delta.py from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clipmint.package_delta import (
    DeltaLayoutError, build_patch as build_file_aware_patch, MAX_PATCH,
)

PACKAGE_RE = re.compile(
    r"clipmint_([0-9]+\.[0-9]+\.[0-9]+[~.]preview[0-9]+\.[0-9]+\.[0-9]+)_amd64\.deb"
)
MAX_BYTES = 350 * 1024 * 1024
MAX_PATCH_RATIO = 0.85


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            sha.update(block)
    return sha.hexdigest()


def package_version(path: Path) -> str:
    match = PACKAGE_RE.fullmatch(path.name)
    if not match or not path.is_file() or path.is_symlink():
        raise ValueError("Expected a regular ClipMint preview Debian package")
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError("Unsupported Debian package size")
    version = match.group(1).replace(".preview", "~preview")
    for key, wanted in (
        ("Package", "clipmint"), ("Version", version), ("Architecture", "amd64"),
    ):
        actual = subprocess.run(
            ["dpkg-deb", "-f", str(path), key],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if actual != wanted:
            raise ValueError(f"Wrong Debian identity: {key}")
    return version


def build_delta(base: Path, target: Path, output: Path) -> bool:
    old = package_version(base)
    new = package_version(target)
    # Use Debian's numeric version order; only forward preview upgrades.
    if subprocess.run(
        ["dpkg", "--compare-versions", old, "lt", new],
        check=False,
    ).returncode:
        return False
    output.mkdir(parents=True, exist_ok=True)
    name = f"clipmint_delta_from_{old}_to_{new}_amd64.bsdiff".replace("~preview", ".preview")
    patch = output / name
    manifest = output / "DELTA.json"
    if patch.exists() or manifest.exists():
        raise ValueError("Refusing to overwrite another delta candidate")
    # Normal production Debian archives use an xz-compressed data.tar.
    # Whole-.deb bsdiff saw the ENTIRE xz stream change for tiny application
    # edits and produced nearly full-size patches. Reuse unchanged tar
    # member file bodies instead, while reconstructing the *exact* .deb.
    # Preserve the legacy binary-diff path only for synthetic test fixtures
    # that have no valid Debian ar/xz structure.
    file_patch = output / name.replace(".bsdiff", ".clipdelta")
    try:
        usable = build_file_aware_patch(base, target, file_patch)
    except DeltaLayoutError as exc:
        # Do not silently spend minutes diffing an already-compressed
        # production package after a file-aware format mismatch.
        print(f"File-aware delta rejected: {exc}", flush=True)
        if target.stat().st_size > 1024 * 1024:
            return False
        usable = None
    if usable is not None:
        if not usable:
            return False
        data = {
            "format": "tar-content-xz-v1",
            "base_version": old,
            "base_sha256": digest(base),
            "target_version": new,
            "target_sha256": digest(target),
            "patch_name": file_patch.name,
            "patch_sha256": digest(file_patch),
            "patch_size": file_patch.stat().st_size,
        }
        manifest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        print(f"File-aware verified patch: {file_patch.stat().st_size} bytes ("
              f"{file_patch.stat().st_size / target.stat().st_size:.1%} of installer)")
        return True
    try:
        bsdiff4.file_diff(str(base), str(target), str(patch))
        if not 32 <= patch.stat().st_size < target.stat().st_size * MAX_PATCH_RATIO:
            return False
        with tempfile.TemporaryDirectory(prefix="clipmint-verify-") as tmp:
            rebuilt = Path(tmp) / target.name
            bsdiff4.file_patch(str(base), str(rebuilt), str(patch))
            if digest(rebuilt) != digest(target):
                raise ValueError("Patch reconstruction did not match target")
        data = {
            "format": "bsdiff4-v1",
            "base_version": old,
            "base_sha256": digest(base),
            "target_version": new,
            "target_sha256": digest(target),
            "patch_name": name,
            "patch_sha256": digest(patch),
            "patch_size": patch.stat().st_size,
        }
        manifest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        return True
    finally:
        if not manifest.exists() and patch.exists():
            patch.unlink()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: build-delta.py OLD.deb NEW.deb OUTPUT_DIR")
    created = build_delta(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    print("Verified delta ready" if created else "No sufficiently small delta; publish full .deb")
