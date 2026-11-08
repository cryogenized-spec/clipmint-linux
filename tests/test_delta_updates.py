"""Offline tests for verified delta downloads and safe full-package fallback."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess

import bsdiff4

from clipmint import updater

OLD_VERSION = "0.6.0~preview1.301.1"
NEW_VERSION = "0.6.0~preview1.302.1"
TAG = "clipmint-preview-302-1"
PREFIX = (
    "https://github.com/cryogenized-spec/clipmint-linux/releases/download/"
    + TAG + "/"
)


class Response:
    status = 200

    def __init__(self, data):
        import io
        self.stream = io.BytesIO(data)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.stream.close()

    def read(self, length):
        return self.stream.read(length)


def make_fixture(base: bytes, target: bytes, patch_data: bytes | None = None):
    binary_patch = bsdiff4.diff(base, target) if patch_data is None else patch_data
    old_hash = hashlib.sha256(base).hexdigest()
    new_hash = hashlib.sha256(target).hexdigest()
    patch_name = f"clipmint_delta_from_{OLD_VERSION}_to_{NEW_VERSION}_amd64.bsdiff"
    manifest = {
        "format": "bsdiff4-v1",
        "base_version": OLD_VERSION, "base_sha256": old_hash,
        "target_version": NEW_VERSION, "target_sha256": new_hash,
        "patch_name": patch_name,
        "patch_sha256": hashlib.sha256(binary_patch).hexdigest(),
        "patch_size": len(binary_patch),
    }
    package_name = f"clipmint_{NEW_VERSION}_amd64.deb"
    release = {
        "draft": False, "prerelease": True, "tag_name": TAG,
        "assets": [
            {"name": package_name, "size": len(target),
             "browser_download_url": PREFIX + package_name},
            {"name": "SHA256SUMS", "size": 150,
             "browser_download_url": PREFIX + "SHA256SUMS"},
            {"name": "DELTA.json", "size": 600,
             "browser_download_url": PREFIX + "DELTA.json"},
            {"name": patch_name, "size": len(binary_patch),
             "browser_download_url": PREFIX + patch_name},
        ],
    }
    candidate = updater.parse_preview_releases(json.dumps([release]).encode())[0]
    checksum = f"{new_hash}  {package_name}\n".encode()
    metadata = json.dumps(manifest).encode()
    return candidate, checksum, metadata, binary_patch


class DeltaUpdateTests(unittest.TestCase):
    def setUp(self):
        self.base = b"prior bundled application contents " * 256
        self.target = self.base[:3000] + b"minor improvement" + self.base[3017:]
        self.candidate, self.checksum, self.metadata, self.patch_bytes = (
            make_fixture(self.base, self.target)
        )

    def download(
        self, base_is_cached=True, patch_bytes=None, *, smaller_only=False,
        unavailable=False,
    ):
        if patch_bytes is None:
            patch_bytes = self.patch_bytes
        with TemporaryDirectory() as root, patch.dict(
            os.environ, {"XDG_CACHE_HOME": root}
        ), patch("clipmint.updater.installed_version",
                 return_value=OLD_VERSION), patch(
            "clipmint.updater.verify_deb"
        ) as verified:
            folder = updater.cached_updates_dir()
            old_path = folder / f"clipmint_{OLD_VERSION}_amd64.deb"
            if base_is_cached:
                old_path.write_bytes(self.base)
            requests = []

            def metadata(url, limit):
                if url.endswith("SHA256SUMS"):
                    return self.checksum
                if url.endswith("DELTA.json"):
                    return self.metadata
                raise AssertionError(f"Unexpected metadata URL: {url}")

            def transfer(request, **_kwargs):
                url = request.full_url
                requests.append(url)
                if url.endswith(".bsdiff"):
                    return Response(patch_bytes)
                if url.endswith(".deb"):
                    return Response(self.target)
                raise AssertionError(f"Unexpected transfer URL: {url}")

            with patch("clipmint.updater.read_bounded", side_effect=metadata), \
                 patch("clipmint.updater.urlopen", side_effect=transfer):
                if unavailable:
                    with self.assertRaises(updater.SmallerUpdateUnavailable):
                        updater.download_verified_preview(
                            self.candidate, smaller_only=smaller_only,
                        )
                    self.assertFalse(
                        (folder / self.candidate.filename).exists()
                    )
                    self.assertFalse(list(folder.glob(".clipmint-*")))
                    return requests
                result = updater.download_verified_preview(
                    self.candidate, smaller_only=smaller_only,
                )
                self.assertEqual(result.read_bytes(), self.target)
                self.assertTrue(result.exists())
                self.assertEqual(verified.call_args.args[1], NEW_VERSION)
                self.assertFalse(list(folder.glob(".clipmint-*")))
                self.assertTrue(old_path.exists() if base_is_cached else True)
                return requests

    def test_small_delta_is_applied_without_downloading_full_deb(self):
        self.assertLess(len(self.patch_bytes), len(self.target) * .85)
        urls = self.download()
        self.assertEqual(urls, [PREFIX + (
            f"clipmint_delta_from_{OLD_VERSION}_to_{NEW_VERSION}_amd64.bsdiff"
        )])

    def test_automatic_delta_only_never_fetches_full_deb_when_base_missing(self):
        urls = self.download(
            base_is_cached=False, smaller_only=True, unavailable=True,
        )
        self.assertEqual(urls, [])

    def test_automatic_delta_only_never_fetches_full_deb_when_patch_corrupt(self):
        urls = self.download(
            patch_bytes=b"damaged", smaller_only=True, unavailable=True,
        )
        self.assertEqual(urls, [
            PREFIX + f"clipmint_delta_from_{OLD_VERSION}_to_{NEW_VERSION}_amd64.bsdiff",
        ])

    def test_automatic_delta_only_stages_verified_patch_without_full_download(self):
        urls = self.download(smaller_only=True)
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].endswith(".bsdiff"))

    def test_automatic_delta_only_skips_patch_over_transfer_cap(self):
        with patch.object(updater, "MAX_AUTO_DELTA_BYTES", len(self.patch_bytes) - 1):
            urls = self.download(smaller_only=True, unavailable=True)
        self.assertEqual(urls, [])

    def test_automatic_delta_only_rejects_invalid_manifest_without_full_download(self):
        manifest = json.loads(self.metadata)
        manifest["target_sha256"] = "f" * 64
        self.metadata = json.dumps(manifest).encode()
        urls = self.download(smaller_only=True, unavailable=True)
        self.assertEqual(urls, [])

    def test_no_exact_cached_base_uses_full_installer(self):
        urls = self.download(base_is_cached=False)
        self.assertEqual(urls, [PREFIX + self.candidate.filename])

    def test_corrupt_transfer_falls_back_to_full_installer(self):
        urls = self.download(patch_bytes=b"damaged")
        self.assertEqual(urls[-1], PREFIX + self.candidate.filename)

    def test_inconsistent_manifest_falls_back_to_full_installer(self):
        manifest = json.loads(self.metadata)
        manifest["target_sha256"] = "f" * 64
        self.metadata = json.dumps(manifest).encode()
        urls = self.download()
        self.assertEqual(urls, [PREFIX + self.candidate.filename])

    def test_manifest_blocks_unknown_formats_and_unsafe_names(self):
        manifest = json.loads(self.metadata)
        for field, value in (
            ("format", "execute-script"), ("base_version", "../../evil"),
            ("patch_name", "../../escape.bsdiff"),
            ("patch_sha256", "not-hex"),
            ("patch_size", 999999999),
            ("target_version", OLD_VERSION),
        ):
            bad = dict(manifest, **{field: value})
            with self.subTest(field=field):
                with self.assertRaises(updater.UpdateError):
                    updater.parse_delta_manifest(
                        self.candidate, json.dumps(bad).encode(),
                        hashlib.sha256(self.target).hexdigest(),
                    )

    def test_retention_keeps_only_current_and_new_verified_installers(self):
        with TemporaryDirectory() as root, patch(
            "clipmint.updater.installed_version", return_value=OLD_VERSION
        ):
            folder = Path(root)
            current = folder / f"clipmint_{OLD_VERSION}_amd64.deb"
            staged = folder / f"clipmint_{NEW_VERSION}_amd64.deb"
            ancient = folder / "clipmint_0.6.0~preview1.299.1_amd64.deb"
            personal = folder / "my-notes.txt"
            for file in (current, staged, ancient, personal):
                file.write_bytes(b"contents")
            updater.prune_superseded_previews(folder, staged)
            self.assertTrue(current.exists())
            self.assertTrue(staged.exists())
            self.assertTrue(personal.exists())
            self.assertFalse(ancient.exists())


class DeltaPublisherTests(unittest.TestCase):
    def test_publisher_reconstructs_exact_target_before_writing_manifest(self):
        path = Path(__file__).resolve().parents[1] / "packaging" / "build-delta.py"
        spec = importlib.util.spec_from_file_location("clipmint_build_delta", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with TemporaryDirectory() as root:
            directory = Path(root)
            base = directory / f"clipmint_{OLD_VERSION}_amd64.deb"
            target = directory / f"clipmint_{NEW_VERSION}_amd64.deb"
            base.write_bytes(b"old" * 5000)
            target.write_bytes(b"old" * 2400 + b"new" + b"old" * 2599)
            with patch.object(
                module, "package_version",
                side_effect=[OLD_VERSION, NEW_VERSION],
            ), patch.object(
                module.subprocess, "run",
                return_value=CompletedProcess([], 0),
            ):
                self.assertTrue(module.build_delta(base, target, directory / "out"))
            manifest = json.loads((directory / "out" / "DELTA.json").read_text())
            self.assertEqual(manifest["target_sha256"], module.digest(target))
            rebuilt = directory / "rebuilt.deb"
            bsdiff4.file_patch(
                str(base), str(rebuilt),
                str(directory / "out" / manifest["patch_name"]),
            )
            self.assertEqual(rebuilt.read_bytes(), target.read_bytes())


if __name__ == "__main__":
    unittest.main()
