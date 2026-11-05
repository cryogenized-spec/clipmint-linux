"""Verifying an encrypted copy before any explicit legacy plaintext deletion."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from nacl.secret import SecretBox
from nacl.utils import random

from clipmint.legacy_cleanup import verify_legacy_history, remove_verified_legacy_history
from clipmint.secure_history import EncryptedClipStore, HistorySecurityError
from clipmint.store import ClipStore


class LegacyHistoryCleanupTests(unittest.TestCase):
    def test_verified_legacy_can_be_removed_only_on_explicit_call(self):
        with TemporaryDirectory() as home:
            path = Path(home) / "history.sqlite3"
            old = ClipStore(path)
            ident = old.add("text", b"Harmless synthetic text", "Harmless synthetic text")
            old.pin(ident, True)
            old.set_tags(ident, ["project"])
            old.save_template("Greeting", "Hello {{name}}")
            encrypted = EncryptedClipStore.migrate_legacy(
                old, Path(home) / "secure-history.sqlite3",
                random(SecretBox.KEY_SIZE),
            )
            old.close()
            try:
                self.assertEqual(verify_legacy_history(encrypted), (path, 1))
                self.assertTrue(path.exists())  # Verification is non-destructive.
                count = remove_verified_legacy_history(encrypted)
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
            path = Path(home) / "history.sqlite3"
            old = ClipStore(path)
            old.add("text", b"First fixture", "First fixture")
            encrypted = EncryptedClipStore.migrate_legacy(
                old, Path(home) / "secure-history.sqlite3",
                random(SecretBox.KEY_SIZE),
            )
            old.add("text", b"Added after migration", "Added after migration")
            old.close()
            try:
                with self.assertRaises(HistorySecurityError):
                    remove_verified_legacy_history(encrypted)
                self.assertTrue(path.exists())
            finally:
                encrypted.close()

    def test_symlinked_legacy_database_not_followed(self):
        with TemporaryDirectory() as home:
            folder = Path(home)
            old = ClipStore(folder / "history.sqlite3")
            old.add("text", b"Test", "Test")
            encrypted = EncryptedClipStore.migrate_legacy(
                old, folder / "secure-history.sqlite3",
                random(SecretBox.KEY_SIZE),
            )
            old.close()
            original = folder / "history.sqlite3"
            moved = folder / "history-archived.sqlite3"
            original.rename(moved)
            original.symlink_to(moved)
            try:
                with self.assertRaises(HistorySecurityError):
                    remove_verified_legacy_history(encrypted)
                self.assertTrue(moved.exists())
            finally:
                encrypted.close()


if __name__ == "__main__":
    unittest.main()
