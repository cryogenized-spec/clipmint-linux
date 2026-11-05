"""No automatic or unsafe removal of unencrypted legacy SQLite history."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sqlite3
import unittest

from nacl.secret import SecretBox
from nacl.utils import random

from clipmint.legacy_cleanup import verify_legacy_history, remove_verified_legacy_history
from clipmint.secure_history import EncryptedClipStore, HistorySecurityError
from clipmint.store import ClipStore


class LegacyHistoryCleanupTests(unittest.TestCase):
    @staticmethod
    def prepare(root: Path):
        original = root / "history.sqlite3"
        old = ClipStore(original)
        ident = old.add("text", b"Harmless synthetic text", "Harmless synthetic text")
        old.pin(ident, True)
        old.set_tags(ident, ["project"])
        old.save_template("Greeting", "Hello {{name}}")
        key = random(SecretBox.KEY_SIZE)
        encrypted = EncryptedClipStore.migrate_legacy(
            old, root / "secure-history.sqlite3", key,
        )
        old.close()
        return original, encrypted, key, ident

    def test_verified_legacy_can_be_removed_only_on_explicit_call(self):
        with TemporaryDirectory() as home:
            path, encrypted, key, ident = self.prepare(Path(home))
            try:
                with patch("clipmint.legacy_cleanup.key_from_secret_service",
                           return_value=key) as lookup:
                    self.assertEqual(verify_legacy_history(encrypted), (path, 1))
                    self.assertTrue(path.exists())
                    count = remove_verified_legacy_history(encrypted)
                self.assertGreaterEqual(lookup.call_count, 3)
                self.assertEqual(count, 1)
                self.assertFalse(path.exists())
                self.assertFalse(Path(str(path) + "-wal").exists())
                self.assertFalse(Path(str(path) + "-shm").exists())
                self.assertEqual(encrypted.get(ident)[1], b"Harmless synthetic text")
                self.assertTrue(encrypted.pinned(ident))
            finally:
                encrypted.close()

    def test_mismatch_leaves_plaintext_history_untouched(self):
        with TemporaryDirectory() as home:
            path, encrypted, key, _ident = self.prepare(Path(home))
            other = ClipStore(path)
            other.add("text", b"Added after migration", "Added after migration")
            other.close()
            try:
                with patch("clipmint.legacy_cleanup.key_from_secret_service",
                           return_value=key):
                    with self.assertRaises(HistorySecurityError):
                        remove_verified_legacy_history(encrypted)
                self.assertTrue(path.exists())
            finally:
                encrypted.close()

    def test_keyring_loss_or_replacement_refuses_removal(self):
        with TemporaryDirectory() as home:
            path, encrypted, _key, _ident = self.prepare(Path(home))
            try:
                with patch("clipmint.legacy_cleanup.key_from_secret_service",
                           return_value=random(SecretBox.KEY_SIZE)):
                    with self.assertRaisesRegex(HistorySecurityError, "key changed"):
                        remove_verified_legacy_history(encrypted)
                with patch("clipmint.legacy_cleanup.key_from_secret_service",
                           side_effect=HistorySecurityError("Keyring locked")):
                    with self.assertRaisesRegex(HistorySecurityError, "Keyring locked"):
                        remove_verified_legacy_history(encrypted)
                self.assertTrue(path.exists())
            finally:
                encrypted.close()

    def test_concurrent_writer_prevents_removal(self):
        with TemporaryDirectory() as home:
            path, encrypted, key, _ident = self.prepare(Path(home))
            writer = sqlite3.connect(path, timeout=0.1, isolation_level=None)
            try:
                writer.execute("BEGIN IMMEDIATE")
                with patch("clipmint.legacy_cleanup.key_from_secret_service",
                           return_value=key):
                    with self.assertRaises(HistorySecurityError):
                        remove_verified_legacy_history(encrypted)
                self.assertTrue(path.exists())
            finally:
                writer.execute("ROLLBACK")
                writer.close()
                encrypted.close()

    def test_idle_open_clipstore_refuses_removal_and_can_resume_writes(self):
        """Regression: WAL BEGIN EXCLUSIVE alone misses idle connections."""
        with TemporaryDirectory() as home:
            path, encrypted, key, _ident = self.prepare(Path(home))
            idle = ClipStore(path)
            try:
                # A normal idle ClipStore with no transaction is a live WAL
                # reader and is allowed to write later.
                self.assertEqual(idle.conn.execute(
                    "PRAGMA journal_mode"
                ).fetchone(), ("wal",))
                with patch("clipmint.legacy_cleanup.key_from_secret_service",
                           return_value=key):
                    with self.assertRaises(HistorySecurityError):
                        remove_verified_legacy_history(encrypted)
                self.assertTrue(path.exists())
                self.assertTrue(idle.add("text", b"New after refusal",
                                         "New after refusal"))
                self.assertTrue(path.exists())
            finally:
                idle.close()
                encrypted.close()

    def test_rollback_journal_is_not_assumed_safe_to_remove(self):
        """Rollback-mode idle handles are not covered by WAL lock semantics."""
        with TemporaryDirectory() as home:
            path, encrypted, key, _ident = self.prepare(Path(home))
            changing = sqlite3.connect(path, isolation_level=None)
            try:
                self.assertEqual(
                    changing.execute("PRAGMA journal_mode=DELETE").fetchone(),
                    ("delete",)
                )
            finally:
                changing.close()
            try:
                with patch("clipmint.legacy_cleanup.key_from_secret_service",
                           return_value=key):
                    with self.assertRaisesRegex(
                        HistorySecurityError, "Unexpected legacy journal mode"
                    ):
                        remove_verified_legacy_history(encrypted)
                self.assertTrue(path.exists())
            finally:
                encrypted.close()

    def test_symlinked_legacy_database_not_followed(self):
        with TemporaryDirectory() as home:
            folder = Path(home)
            original, encrypted, key, _ident = self.prepare(folder)
            moved = folder / "history-archived.sqlite3"
            original.rename(moved)
            original.symlink_to(moved)
            try:
                with patch("clipmint.legacy_cleanup.key_from_secret_service",
                           return_value=key):
                    with self.assertRaises(HistorySecurityError):
                        remove_verified_legacy_history(encrypted)
                self.assertTrue(moved.exists())
            finally:
                encrypted.close()


if __name__ == "__main__":
    unittest.main()
