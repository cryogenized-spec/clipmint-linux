"""Offline, byte-identical file-aware preview delta tests using real dpkg archives."""
from __future__ import annotations

import os
import random
import lzma
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from clipmint.package_delta import (
    DeltaLayoutError, _ar_members, apply_patch, build_patch,
)


def make_deb(base: Path, version: str, *, modified: bool, compression: str = "xz") -> Path:
    root = base / ("new" if modified else "old")
    (root / "DEBIAN").mkdir(parents=True)
    (root / "opt" / "clipmint").mkdir(parents=True)
    (root / "DEBIAN" / "control").write_text(
        f"Package: clipmint\nVersion: {version}\nArchitecture: amd64\n"
        "Maintainer: ClipMint tests\nDescription: Delta test\n"
    )
    # The unchanged random payload makes compressed-.deb bsdiff impractical,
    # but it must cost zero bytes in the new file-aware patch.
    (root / "opt" / "clipmint" / "unchanged.bin").write_bytes(
        b"stable-prefix" + random.Random(42).randbytes(4 * 1024 * 1024)
    )
    (root / "opt" / "clipmint" / "changed.txt").write_bytes(
        ("updated app logic" if modified else "original app logic").encode()
    )
    output = base / ("new.deb" if modified else "old.deb")
    subprocess.run(
        ["dpkg-deb", "--root-owner-group", f"-Z{compression}", "--threads-max=1", "--build", str(root), str(output)],
        capture_output=True, text=True, check=True,
    )
    return output


class FileAwareDebianPatchTests(unittest.TestCase):
    def test_rebuilds_exact_compressed_debian_archive(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            old = make_deb(folder, "0.6.0~preview1.301.1", modified=False)
            new = make_deb(folder, "0.6.0~preview1.302.1", modified=True)
            patch = folder / "changes.clipdelta"
            self.assertTrue(build_patch(old, new, patch))
            self.assertLess(patch.stat().st_size, new.stat().st_size // 4)
            output = folder / "reconstructed.deb"
            apply_patch(old, patch, output)
            self.assertEqual(output.read_bytes(), new.read_bytes())
            self.assertEqual(
                [x[0] for x in _ar_members(output.read_bytes())],
                ["debian-binary", "control.tar.xz", "data.tar.xz"],
            )

    def test_old_zstd_package_can_upgrade_to_new_xz_release(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            old = make_deb(
                folder, "0.6.0~preview1.301.1",
                modified=False, compression="zstd",
            )
            new = make_deb(folder, "0.6.0~preview1.302.1", modified=True)
            patch = folder / "changes.clipdelta"
            self.assertTrue(build_patch(old, new, patch))
            self.assertLess(patch.stat().st_size, new.stat().st_size // 4)
            rebuilt = folder / "rebuilt.deb"
            apply_patch(old, patch, rebuilt)
            self.assertEqual(rebuilt.read_bytes(), new.read_bytes())

    def test_wrong_cached_base_cannot_rebuild_official_package(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            old = make_deb(folder, "0.6.0~preview1.301.1", modified=False)
            new = make_deb(folder, "0.6.0~preview1.302.1", modified=True)
            patch = folder / "changes.clipdelta"
            self.assertTrue(build_patch(old, new, patch))
            damaged = folder / "wrong.deb"
            contents = bytearray(old.read_bytes())
            contents[-40] ^= 1
            damaged.write_bytes(contents)
            with self.assertRaises((DeltaLayoutError, OSError, ValueError, lzma.LZMAError)):
                apply_patch(damaged, patch, folder / "invalid.deb")

    def test_unknown_ar_layout_rejected(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            invalid = folder / "invalid.deb"
            invalid.write_bytes(b"not a Debian package")
            with self.assertRaises(DeltaLayoutError):
                _ar_members(invalid.read_bytes())


if __name__ == "__main__":
    unittest.main()
