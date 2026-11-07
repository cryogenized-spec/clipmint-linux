"""Offline, adversarial update tests: no network or package installation."""
from __future__ import annotations

import hashlib
import http.client
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess

from clipmint import updater


def preview_fixture(version="0.6.0~preview1.301.1", tag="clipmint-preview-301-1"):
    name = f"clipmint_{version}_amd64.deb"
    prefix = f"https://github.com/cryogenized-spec/clipmint-linux/releases/download/{tag}/"
    return {
        "draft": False, "prerelease": True, "tag_name": tag,
        "assets": [
            {"name": name, "size": 150, "browser_download_url": prefix + name},
            {"name": "SHA256SUMS", "size": 100,
             "browser_download_url": prefix + "SHA256SUMS"},
        ],
    }


class FakeResponse(io.BytesIO):
    status = 200


class UpdaterTests(unittest.TestCase):
    def test_only_our_complete_immutable_preview_release_is_accepted(self):
        good = preview_fixture()
        unexpected_origin = preview_fixture(tag="clipmint-preview-301-2")
        unexpected_origin["assets"][0]["browser_download_url"] = (
            "https://evil.invalid/clipmint_0.6.0~preview1.301.1_amd64.deb"
        )
        malformed = preview_fixture(tag="clipmint-preview-301-3")
        malformed["assets"].pop()
        old_release = preview_fixture(tag="v0.3.0")
        candidates = updater.parse_preview_releases(json.dumps([
            good, unexpected_origin, malformed, old_release,
        ]).encode())
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].version, "0.6.0~preview1.301.1")
        self.assertEqual(candidates[0].filename, good["assets"][0]["name"])

    def test_github_normalized_preview_asset_and_legacy_checksum(self):
        item = preview_fixture()
        name = item["assets"][0]["name"]
        normalized = name.replace("~preview", ".preview")
        item["assets"][0]["name"] = normalized
        item["assets"][0]["browser_download_url"] = (
            item["assets"][0]["browser_download_url"].replace(name, normalized)
        )
        release = updater.parse_preview_releases(json.dumps([item]).encode())
        self.assertEqual(len(release), 1)
        self.assertEqual(release[0].version, "0.6.0~preview1.301.1")
        self.assertEqual(release[0].filename, normalized)
        expected = "b" * 64
        # Older releases had an original Debian basename in SHA256SUMS,
        # even though GitHub renamed the public asset to .preview.
        self.assertEqual(updater.expected_checksum(
            f"{expected}  {name}".encode(), normalized
        ), expected)

    def test_reject_malformed_or_unsafe_release_urls(self):
        url = preview_fixture()["assets"][0]["browser_download_url"]
        self.assertEqual(
            updater.validate_asset_url(
                url, "clipmint-preview-301-1",
                "clipmint_0.6.0~preview1.301.1_amd64.deb",
            ), url,
        )
        for bad in (
            url.replace("https://", "http://"),
            url.replace("github.com", "github.com.evil.invalid"),
            url.replace("clipmint-linux", "another-project"),
            url + "?redirect=evil",
            url.replace("preview-301-1", "preview-300-1"),
        ):
            with self.assertRaises(updater.UpdateError):
                updater.validate_asset_url(
                    bad, "clipmint-preview-301-1",
                    "clipmint_0.6.0~preview1.301.1_amd64.deb",
                )

    def test_debian_comparison_rejects_downgrades(self):
        def simulated(command, **_kwargs):
            self.assertEqual(command[:2], ["/usr/bin/dpkg", "--compare-versions"])
            old, comparator, candidate = command[2:]
            self.assertEqual(comparator, "lt")
            return CompletedProcess(command, int(old == candidate), stdout=b"")
        with patch("clipmint.updater.subprocess.run", side_effect=simulated):
            self.assertFalse(updater.version_is_newer(
                "0.6.0~preview1.301.1", "0.6.0~preview1.301.1"
            ))
            self.assertTrue(updater.version_is_newer(
                "0.6.0~preview1.301.1", "0.6.0~preview1.300.1"
            ))

    def test_only_newer_published_release_is_offered(self):
        item = preview_fixture()
        with patch("clipmint.updater.installed_version",
                   return_value="0.6.0~preview1.300.1"), \
             patch("clipmint.updater.read_bounded",
                   return_value=json.dumps([item]).encode()), \
             patch("clipmint.updater.version_is_newer", return_value=True):
            found = updater.check_for_preview_update()
            self.assertIsNotNone(found)
            self.assertEqual(found.version, "0.6.0~preview1.301.1")
        with patch("clipmint.updater.installed_version", return_value=None), \
             patch("clipmint.updater.read_bounded") as network:
            self.assertIsNone(updater.check_for_preview_update())
            network.assert_not_called()

    def test_sha256_manifest_must_identify_exactly_one_asset(self):
        name = "clipmint_0.6.0~preview1.301.1_amd64.deb"
        checksum = "a" * 64
        self.assertEqual(
            updater.expected_checksum((checksum + "  " + name + "\n").encode(), name),
            checksum,
        )
        for bad in (
            checksum + "  different.deb\n",
            checksum + "  " + name + "\n" + checksum + "  other.deb\n",
            "../../evil\n",
        ):
            with self.assertRaises(updater.UpdateError):
                updater.expected_checksum(bad.encode(), name)

    def test_dpkg_inspection_must_match_identity(self):
        with TemporaryDirectory() as root:
            pkg = Path(root) / "test.deb"
            with patch("clipmint.updater.subprocess.run",
                       return_value=CompletedProcess(
                           [], 0,
                           stdout=("Package: clipmint\n"
                                   "Version: 0.6.0~preview1.301.1\n"
                                   "Architecture: amd64\n"),
                       )):
                updater.verify_deb(pkg, "0.6.0~preview1.301.1")
            with patch("clipmint.updater.subprocess.run",
                       return_value=CompletedProcess(
                           [], 0, stdout=(
                               "Package: another-package\n"
                               "Version: 0.6.0~preview1.301.1\n"
                               "Architecture: amd64\n"
                           ),
                       )):
                with self.assertRaises(updater.UpdateError):
                    updater.verify_deb(pkg, "0.6.0~preview1.301.1")

    def test_atomic_download_accepts_verified_bytes_only(self):
        candidate = updater.parse_preview_releases(
            json.dumps([preview_fixture()]).encode()
        )[0]
        payload = b"Fake offline binary fixture (never executed)"
        sha = hashlib.sha256(payload).hexdigest()
        with TemporaryDirectory() as root, patch.dict(
            os.environ, {"XDG_CACHE_HOME": root}
        ), patch("clipmint.updater.read_bounded",
                 return_value=f"{sha}  {candidate.filename}\n".encode()), \
             patch("clipmint.updater.urlopen",
                   side_effect=lambda *_args, **_kw: FakeResponse(payload)), \
             patch("clipmint.updater.verify_deb") as verified:
            cache = updater.cached_updates_dir()
            old = cache / "clipmint_0.6.0~preview1.299.1_amd64.deb"
            old.write_bytes(b"superseded 100MB package fixture")
            unrelated = cache / "personal-notes.txt"
            unrelated.write_text("must survive update cleanup")
            path = updater.download_verified_preview(candidate)
            self.assertFalse(old.exists(), "Previous installer should be pruned")
            self.assertEqual(unrelated.read_text(), "must survive update cleanup")
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(verified.call_args.args[1], candidate.version)
            self.assertEqual(
                list(path.parent.glob(".clipmint-preview-*")), [],
                "Temporary archive must be removed after atomic installation",
            )
            again = updater.download_verified_preview(candidate)
            self.assertEqual(path, again)
            self.assertEqual(verified.call_count, 2)
            path.write_bytes(b"corrupted old cache")
            recovered = updater.download_verified_preview(candidate)
            self.assertEqual(recovered.read_bytes(), payload)

    def test_truncated_http_transfer_is_a_retryable_update_error(self):
        class TruncatedResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self, *_args):
                raise http.client.IncompleteRead(b"partial", 200)

        with patch("clipmint.updater.urlopen",
                   return_value=TruncatedResponse()):
            with self.assertRaises(updater.UpdateError):
                updater.read_bounded(updater.API_URL, updater.MAX_API_BYTES)

    def test_checksum_mismatch_never_publishes_a_cached_file(self):
        candidate = updater.parse_preview_releases(
            json.dumps([preview_fixture()]).encode()
        )[0]
        with TemporaryDirectory() as root, patch.dict(
            os.environ, {"XDG_CACHE_HOME": root}
        ), patch("clipmint.updater.read_bounded",
                 return_value=(("f" * 64) + "  " + candidate.filename).encode()), \
             patch("clipmint.updater.urlopen",
                   side_effect=lambda *_args, **_kw: FakeResponse(b"not trusted")
             ):
            with self.assertRaises(updater.UpdateError):
                updater.download_verified_preview(candidate)
            self.assertFalse((Path(root) / "clipmint" / "updates" /
                              candidate.filename).exists())


if __name__ == "__main__":
    unittest.main()
