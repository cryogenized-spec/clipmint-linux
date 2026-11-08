"""Offline tests: multiple trusted preview bases and local Downloads reuse.

No network, installed package, or real user Downloads directory is accessed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import bsdiff4
from clipmint import updater


class FakeResponse:
    status = 200

    def __init__(self, value):
        import io
        self.stream = io.BytesIO(value)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.stream.close()

    def read(self, size):
        return self.stream.read(size)


class BootstrapPreviewTests(unittest.TestCase):
    def setUp(self):
        self.old_version = "0.6.0~preview1.227.1"
        self.new_version = "0.6.0~preview1.246.1"
        self.old = (b"existing clipmint data " * 1000)
        self.new = self.old[:2500] + b"replaced" + self.old[2508:]
        self.patch = bsdiff4.diff(self.old, self.new)
        self.old_hash = hashlib.sha256(self.old).hexdigest()
        self.new_hash = hashlib.sha256(self.new).hexdigest()
        self.tag = "clipmint-preview-246-1"
        self.root = ("https://github.com/cryogenized-spec/clipmint-linux/"
                     "releases/download/" + self.tag + "/")
        self.pkg = "clipmint_0.6.0.preview1.246.1_amd64.deb"
        self.patch_name = ("clipmint_delta_from_0.6.0.preview1.227.1_to_"
                           "0.6.0.preview1.246.1_amd64.bsdiff")
        self.manifest = {
            "format": "bsdiff4-v1",
            "base_version": self.old_version,
            "base_sha256": self.old_hash,
            "target_version": self.new_version,
            "target_sha256": self.new_hash,
            "patch_name": self.patch_name,
            "patch_sha256": hashlib.sha256(self.patch).hexdigest(),
            "patch_size": len(self.patch),
        }
        other = dict(self.manifest)
        other["base_version"] = "0.6.0~preview1.240.1"
        other["base_sha256"] = "a" * 64
        other["patch_name"] = ("clipmint_delta_from_0.6.0.preview1.240.1_to_"
                               "0.6.0.preview1.246.1_amd64.bsdiff")
        self.other_manifest = other
        assets = [
            {"name": self.pkg, "size": len(self.new),
             "browser_download_url": self.root + self.pkg},
            {"name": "SHA256SUMS", "size": 106,
             "browser_download_url": self.root + "SHA256SUMS"},
            {"name": "DELTA.json", "size": 500,
             "browser_download_url": self.root + "DELTA.json"},
            {"name": "DELTA-227.json", "size": 500,
             "browser_download_url": self.root + "DELTA-227.json"},
            {"name": self.patch_name, "size": len(self.patch),
             "browser_download_url": self.root + self.patch_name},
        ]
        release = {"draft": False, "prerelease": True,
                   "tag_name": self.tag, "assets": assets}
        self.candidate = updater.parse_preview_releases(
            json.dumps([release]).encode()
        )[0]

    def test_immutable_metadata_supports_multiple_delta_bases(self):
        self.assertEqual(self.candidate.delta_manifest_url,
                         self.root + "DELTA.json")
        self.assertEqual(self.candidate.delta_manifest_urls,
                         (self.root + "DELTA-227.json",))

    def _stage(self, *, valid_local: bool):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            downloads = home / "Downloads"
            downloads.mkdir(parents=True)
            archive = (downloads /
                       "clipmint_0.6.0.preview1.227.1_amd64.deb")
            archive.write_bytes(self.old if valid_local else b"damaged")
            queries, transfers = [], []

            def metadata(url, _limit):
                queries.append(url)
                if url.endswith("SHA256SUMS"):
                    return f"{self.new_hash}  {self.pkg}\n".encode()
                if url.endswith("DELTA.json"):
                    return json.dumps(self.other_manifest).encode()
                if url.endswith("DELTA-227.json"):
                    return json.dumps(self.manifest).encode()
                raise AssertionError(url)

            def transfer(request, **_options):
                transfers.append(request.full_url)
                if request.full_url == self.root + self.patch_name:
                    return FakeResponse(self.patch)
                raise AssertionError("Unexpected installer download")

            with patch.dict(os.environ, {"XDG_CACHE_HOME": str(Path(tmp) / "cache")}), \
                 patch("clipmint.updater.Path.home", return_value=home), \
                 patch("clipmint.updater.installed_version",
                       return_value=self.old_version), \
                 patch("clipmint.updater.verify_deb") as verified, \
                 patch("clipmint.updater.read_bounded", side_effect=metadata), \
                 patch("clipmint.updater.urlopen", side_effect=transfer):
                if valid_local:
                    installer = updater.download_verified_preview(
                        self.candidate, smaller_only=True
                    )
                    self.assertEqual(installer.read_bytes(), self.new)
                    self.assertEqual(archive.read_bytes(), self.old)
                    self.assertEqual(verified.call_count, 2)
                else:
                    with self.assertRaises(updater.SmallerUpdateUnavailable):
                        updater.download_verified_preview(
                            self.candidate, smaller_only=True
                        )
                    self.assertFalse(
                        (updater.cached_updates_dir() / self.pkg).exists()
                    )
                self.assertEqual(
                    queries[:3],
                    [self.root + "SHA256SUMS", self.root + "DELTA.json",
                     self.root + "DELTA-227.json"],
                )
                self.assertEqual(
                    transfers, [self.root + self.patch_name] if valid_local else []
                )

    def test_reuses_exact_hash_checked_downloads_file_without_full_transfer(self):
        self._stage(valid_local=True)

    def test_rejects_wrong_local_file_without_downloading_full_installer(self):
        self._stage(valid_local=False)


if __name__ == "__main__":
    unittest.main()
