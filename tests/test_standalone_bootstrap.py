"""Offline acceptance for the small-data Preview 227 bootstrap.

Generates a real package delta, launches the actual concatenated standalone
bootstrap Python module, mocks ONLY the network source and user confirmation,
and checks that the output is exactly the target Debian file.
"""
from __future__ import annotations

import bz2
import hashlib
import importlib.util
import json
import os
import random
import zipfile
from pathlib import Path
import runpy
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import bsdiff4
from clipmint import package_delta

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "packaging" / "generate-preview-bootstrap.py"


def _make_deb(directory: Path, version: str, *, modified: bool) -> Path:
    root = directory / ("new" if modified else "old")
    (root / "DEBIAN").mkdir(parents=True)
    (root / "opt" / "clipmint").mkdir(parents=True)
    (root / "DEBIAN" / "control").write_text(
        f"Package: clipmint\nVersion: {version}\nArchitecture: amd64\n"
        "Maintainer: ClipMint tests\nDescription: Tiny bootstrap test\n"
    )
    (root / "opt" / "clipmint" / "unchanged.bin").write_bytes(
        b"same data" * (1024 * 128)
    )
    (root / "opt" / "clipmint" / "changed.txt").write_text(
        "Improved" if modified else "Original"
    )
    # Force at least one native BSDIFF40 payload in the release delta, so
    # the standalone Python-only decoder is exercised end-to-end.
    body = random.Random(83).randbytes(262_144)
    if modified:
        body = body[:100_000] + b"NEW-REPAIR-LOGIC!" + body[100_017:]
    (root / "opt" / "clipmint" / "changed.bin").write_bytes(body)
    output = directory / ("target.deb" if modified else "base.deb")
    subprocess.run(
        ["dpkg-deb", "--root-owner-group", "-Zxz",
         "--threads-max=1", "--build", str(root), str(output)],
        capture_output=True, check=True,
    )
    return output


class BootstrapPreviewTests(unittest.TestCase):
    def test_pure_python_bsdiff40_matches_native_decoder(self):
        import random
        original = random.Random(11).randbytes(170_000)
        modified = original[:80_000] + b"CHANGED-CODE" + original[80_012:]
        delta = bsdiff4.diff(original, modified)
        self.assertEqual(
            package_delta._bsdiff_apply(original, delta, len(modified)),
            modified,
        )
        for invalid in (b"", b"NOTBSDIFF" + delta[8:], delta[:27]):
            with self.subTest(invalid=invalid[:8]):
                with self.assertRaises(package_delta.DeltaLayoutError):
                    package_delta._bsdiff_apply(
                        original, invalid, len(modified)
                    )

    def test_stdlib_decoder_accepts_cursor_only_control_records(self):
        # A valid BSDIFF40 operation may move the old cursor without
        # emitting any output. The real original release diff can do this.
        def signed(n):
            magnitude = abs(n)
            encoded = bytes(
                (magnitude >> (8 * i)) & 0xFF for i in range(7)
            )
            return encoded + bytes([
                (magnitude >> 56) | (0x80 if n < 0 else 0)
            ])

        control = (
            signed(0) + signed(0) + signed(2)
            + signed(3) + signed(0) + signed(0)
        )
        control_z = bz2.compress(control)
        diff_z = bz2.compress(b"\x00" * 3)
        extra_z = bz2.compress(b"")
        delta = (b"BSDIFF40" + signed(len(control_z))
                 + signed(len(diff_z)) + signed(3)
                 + control_z + diff_z + extra_z)
        self.assertEqual(
            package_delta._bsdiff_apply(b"abcdef", delta, 3), b"cde"
        )

    def test_release_pinned_bootstrap_reconstructs_verified_deb_offline(self):
        old_version = "0.6.0~preview1.227.1"
        target_version = "0.6.0~preview1.249.1"
        tag = "clipmint-preview-249-1"
        with TemporaryDirectory() as work:
            root = Path(work)
            home = root / "home"
            downloads = home / "Downloads"
            downloads.mkdir(parents=True)
            old = _make_deb(root, old_version, modified=False)
            target = _make_deb(root, target_version, modified=True)
            old_saved = downloads / "clipmint_0.6.0.preview1.227.1_amd64.deb"
            old_saved.write_bytes(old.read_bytes())
            patch_path = root / "upgrade.clipdelta"
            self.assertTrue(package_delta.build_patch(old, target, patch_path))
            patch_bytes = patch_path.read_bytes()
            with zipfile.ZipFile(patch_path) as archive:
                metadata = json.loads(archive.read("meta.json"))
                sources = [
                    p["source"]
                    for member in metadata["ar"]
                    if member["payload"]["type"] == "tarxz"
                    for p in member["payload"]["parts"]
                ]
                self.assertIn("bsdiff", sources)
            new_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            name = "clipmint_0.6.0.preview1.249.1_amd64.deb"
            patch_name = ("clipmint_delta_from_0.6.0.preview1.227.1_to_"
                          "0.6.0.preview1.249.1_amd64.clipdelta")
            manifest = {
                "format": package_delta.FORMAT,
                "base_version": old_version,
                "base_sha256": hashlib.sha256(old.read_bytes()).hexdigest(),
                "target_version": target_version,
                "target_sha256": new_hash,
                "patch_name": patch_name,
                "patch_sha256": hashlib.sha256(patch_bytes).hexdigest(),
                "patch_size": len(patch_bytes),
            }
            release_files = {
                "SHA256SUMS": f"{new_hash}  {name}\n".encode(),
                "DELTA-227.json": json.dumps(manifest).encode(),
                patch_name: patch_bytes,
            }
            spec = importlib.util.spec_from_file_location(
                "clipmint_bootstrap_generate", GENERATOR_PATH,
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            helper = root / "clipmint-bootstrap-from-227.py"
            module.generate(tag, target_version, helper)
            script = helper.read_text()
            self.assertTrue(script.startswith("#!/usr/bin/python3"))
            self.assertIn(tag, script)
            self.assertNotIn("__CLIPMINT_RELEASE_", script)
            scope = runpy.run_path(str(helper), run_name="bootstrap_acceptance")
            bootstrap = scope["_bootstrap_run"]
            calls = []

            def retrieve(url, maximum):
                key = url.rsplit("/", 1)[-1]
                calls.append(key)
                self.assertIn(key, release_files)
                self.assertLessEqual(len(release_files[key]), maximum)
                return release_files[key]

            variables = bootstrap.__globals__
            with patch.dict(variables, {"_bootstrap_fetch": retrieve}), \
                 patch("pathlib.Path.home", return_value=home), \
                 patch.dict(os.environ, {
                     "XDG_CACHE_HOME": str(root / "cache"),
                 }), patch("builtins.input", return_value="y"):
                bootstrap()
            completed = (root / "cache" / "clipmint" / "updates" / name)
            self.assertEqual(completed.read_bytes(), target.read_bytes())
            self.assertEqual(old_saved.read_bytes(), old.read_bytes())
            self.assertEqual(calls, ["SHA256SUMS", "DELTA-227.json", patch_name])

    def test_release_publisher_exports_standalone_helper_and_digest(self):
        workflow = (ROOT / ".github/workflows/build-linux.yml").read_text()
        self.assertIn("packaging/generate-preview-bootstrap.py", workflow)
        self.assertIn("dist-packages/clipmint-bootstrap-from-227.py", workflow)
        self.assertIn("BOOTSTRAP-SHA256SUMS", workflow)
        self.assertIn("sha256sum --check BOOTSTRAP-SHA256SUMS", workflow)
        source = (ROOT / "clipmint" / "package_delta.py").read_text()
        self.assertNotIn("\nimport bsdiff4\n", source)


if __name__ == "__main__":
    unittest.main()
