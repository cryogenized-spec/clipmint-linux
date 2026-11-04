"""Archive snapshot security and integrity regression tests.

All values are synthetic; no user credentials or actual clipboard history.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import stat
from tempfile import TemporaryDirectory
import unittest

from nacl import utils
from nacl.secret import SecretBox

from clipmint.archive_backup import backup_archive, ArchiveBackupError
from clipmint.store import ClipStore
from clipmint.secure_history import EncryptedClipStore


class ArchiveBackupTests(unittest.TestCase):
    def test_live_wal_snapshot_and_0600_permissions(self):
        with TemporaryDirectory() as root:
            src = ClipStore(Path(root) / "live.sqlite3")
            target = Path(root) / "archive.sqlite3"
            try:
                src.add("text", b"hello archive", "hello archive")
                src.add_bin("Project")
                src.add("text", b"project notes", "project notes", "Project")
                self.assertEqual(backup_archive(src.conn, target), target)
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                # A verified single-file backup includes the complete logical
                # data even if the live source was operating with WAL.
                reader = sqlite3.connect(target)
                try:
                    self.assertEqual(
                        reader.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                    )
                    self.assertEqual(
                        reader.execute("SELECT COUNT(*) FROM clips").fetchone()[0], 2
                    )
                    self.assertEqual(
                        reader.execute(
                            "SELECT content FROM clips WHERE bin='Project'"
                        ).fetchone()[0],
                        b"project notes",
                    )
                finally:
                    reader.close()
                src.add("text", b"new after backup", "new after backup")
                reader = sqlite3.connect(target)
                try:
                    self.assertEqual(
                        reader.execute("SELECT COUNT(*) FROM clips").fetchone()[0], 2
                    )
                finally:
                    reader.close()
            finally:
                src.close()

    def test_existing_destination_is_untouched_without_explicit_overwrite(self):
        with TemporaryDirectory() as root:
            src = ClipStore(Path(root) / "source.sqlite3")
            dest = Path(root) / "archive.sqlite3"
            try:
                src.add("text", b"fixture", "fixture")
                dest.write_bytes(b"preexisting user content")
                with self.assertRaises(FileExistsError):
                    backup_archive(src.conn, dest)
                self.assertEqual(dest.read_bytes(), b"preexisting user content")
                backup_archive(src.conn, dest, overwrite=True)
                self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o600)
                self.assertEqual(
                    sqlite3.connect(dest).execute(
                        "SELECT COUNT(*) FROM clips"
                    ).fetchone()[0], 1
                )
                self.assertFalse(list(Path(root).glob("*.building")))
            finally:
                src.close()

    def test_symlink_and_live_source_overwrite_rejected(self):
        with TemporaryDirectory() as root:
            src = ClipStore(Path(root) / "history.sqlite3")
            alias = Path(root) / "redirect.sqlite3"
            alias.symlink_to(src.path)
            try:
                with self.assertRaises(ArchiveBackupError):
                    backup_archive(src.conn, src.path, overwrite=True)
                with self.assertRaises(ArchiveBackupError):
                    backup_archive(src.conn, alias, overwrite=True)
                self.assertTrue(src.path.exists())
            finally:
                src.close()

    def test_duplicate_bin_creation_rolls_back_and_backup_still_works(self):
        with TemporaryDirectory() as root:
            src = ClipStore(Path(root) / "live.sqlite3")
            target = Path(root) / "archive.sqlite3"
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    src.add_bin("Work")
                self.assertFalse(src.conn.in_transaction)
                src.add("text", b"archive works", "archive works")
                backup_archive(src.conn, target)
                self.assertEqual(
                    sqlite3.connect(target).execute(
                        "SELECT COUNT(*) FROM clips"
                    ).fetchone()[0], 1
                )
            finally:
                src.close()

    def test_rejects_open_source_transaction_without_hanging(self):
        with TemporaryDirectory() as root:
            src = ClipStore(Path(root) / "live.sqlite3")
            target = Path(root) / "archive.sqlite3"
            try:
                src.add("text", b"committed row", "committed row")
                src.conn.execute(
                    "INSERT INTO bins(name,position) VALUES('uncommitted', 999)"
                )
                self.assertTrue(src.conn.in_transaction)
                with self.assertRaisesRegex(
                    ArchiveBackupError, "unfinished database write"
                ):
                    backup_archive(src.conn, target, timeout_seconds=0.25)
                self.assertFalse(target.exists())
                src.conn.rollback()
                backup_archive(src.conn, target)
                self.assertTrue(target.exists())
            finally:
                src.close()

    def test_refuses_overwrite_target_with_live_wal_sidecars(self):
        with TemporaryDirectory() as root:
            src = ClipStore(Path(root) / "live.sqlite3")
            target = Path(root) / "target.sqlite3"
            other = sqlite3.connect(target)
            try:
                src.add("text", b"good new data", "good new data")
                other.execute("PRAGMA journal_mode=WAL")
                other.execute("CREATE TABLE old_data(value TEXT)")
                other.execute(
                    "INSERT INTO old_data(value) VALUES('existing important data')"
                )
                other.commit()
                other.execute("INSERT INTO old_data(value) VALUES('still open')")
                other.commit()
                self.assertTrue(Path(str(target) + "-wal").exists())
                with self.assertRaisesRegex(
                    ArchiveBackupError, "WAL/journal sidecars"
                ):
                    backup_archive(src.conn, target, overwrite=True)
                self.assertEqual(
                    other.execute("SELECT COUNT(*) FROM old_data").fetchone()[0], 2
                )
            finally:
                other.close()
                src.close()

    def test_refuses_unsafe_world_writable_nonsticky_parent(self):
        with TemporaryDirectory() as root:
            directory = Path(root) / "insecure"
            directory.mkdir()
            directory.chmod(0o777)
            src = ClipStore(Path(root) / "source.sqlite3")
            try:
                with self.assertRaisesRegex(
                    ArchiveBackupError, "private backup folder"
                ):
                    backup_archive(src.conn, directory / "archive.sqlite3")
                self.assertEqual(list(directory.iterdir()), [])
            finally:
                src.close()

    def test_foreign_owned_sticky_parent_is_not_trusted(self):
        from unittest.mock import patch
        with TemporaryDirectory() as root:
            directory = Path(root) / "shared-sticky"
            directory.mkdir()
            directory.chmod(0o1777)
            src = ClipStore(Path(root) / "source.sqlite3")
            try:
                # Simulate a destination directory owned by a different
                # account than the active caller, as with /tmp.
                with patch(
                    "clipmint.archive_backup.os.geteuid",
                    return_value=os.geteuid() + 1,
                ):
                    with self.assertRaisesRegex(
                        ArchiveBackupError, "private backup folder"
                    ):
                        backup_archive(
                            src.conn, directory / "private-copy.sqlite3"
                        )
                self.assertEqual(list(directory.iterdir()), [])
            finally:
                src.close()

    def test_no_private_staging_files_left_after_backup(self):
        with TemporaryDirectory() as root:
            src = ClipStore(Path(root) / "source.sqlite3")
            target = Path(root) / "archive.sqlite3"
            try:
                src.add("text", b"test", "test")
                backup_archive(src.conn, target)
                self.assertFalse(
                    list(Path(root).glob(".clipmint-backup-*"))
                )
            finally:
                src.close()

    def test_encrypted_history_remains_ciphertext_without_key_export(self):
        with TemporaryDirectory() as root:
            key = utils.random(SecretBox.KEY_SIZE)
            src = EncryptedClipStore(Path(root) / "secure.sqlite3", key)
            dest = Path(root) / "encrypted-archive.sqlite3"
            try:
                src.add("text", b"FAKE_PRIVATE_TEST_PAYLOAD_XYZ", "masked")
                backup_archive(src.conn, dest)
                self.assertNotIn(b"FAKE_PRIVATE_TEST_PAYLOAD_XYZ",
                                 dest.read_bytes())
                reopened = EncryptedClipStore(dest, key)
                try:
                    self.assertEqual(
                        reopened.search()[0].preview, "masked"
                    )
                finally:
                    reopened.close()
            finally:
                src.close()


if __name__ == "__main__":
    unittest.main()
