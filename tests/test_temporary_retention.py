"""Opt-in Temporary-bin retention regression tests (synthetic data only)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from nacl.secret import SecretBox
from nacl import utils

from clipmint.secure_history import EncryptedClipStore
from clipmint.store import ClipStore


NOW = datetime(2026, 11, 4, 19, 30, tzinfo=timezone.utc)


def age_item(store: ClipStore, clip_id: int, age: timedelta) -> None:
    timestamp = NOW - age
    store.conn.execute(
        "UPDATE clips SET created_at=? WHERE id=?",
        (timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
         clip_id),
    )
    store.conn.commit()


class TemporaryRetentionTests(unittest.TestCase):
    def exercise_store(self, store: ClipStore):
        old_temp = store.add("text", b"old temporary text", "old temporary text",
                             "Temporary")
        recent_temp = store.add("text", b"new temporary text", "new temporary text",
                                "Temporary")
        pinned_temp = store.add("text", b"pinned temporary text", "pinned temporary text",
                                "Temporary")
        old_work = store.add("text", b"old work note", "old work note", "Work")
        old_personal = store.add("text", b"old personal note", "old personal note",
                                 "Personal")
        store.pin(pinned_temp, True)
        for ident in (old_temp, pinned_temp, old_work, old_personal):
            age_item(store, ident, timedelta(days=3))
        age_item(store, recent_temp, timedelta(minutes=7))
        self.assertEqual(store.expire_temporary_unpinned(now=NOW), 1)
        self.assertIsNone(store.get(old_temp))
        self.assertEqual(store.count("Temporary"), 2)
        self.assertIsNotNone(store.get(recent_temp))
        self.assertIsNotNone(store.get(pinned_temp))
        self.assertIsNotNone(store.get(old_work))
        self.assertIsNotNone(store.get(old_personal))
        self.assertEqual(store.expire_temporary_unpinned(now=NOW), 0)
        # A second, separately opted-in operation deletes unpinned recent
        # Temporary items on a normal quit, not all collections.
        self.assertEqual(store.clear_temporary_unpinned(), 1)
        self.assertIsNone(store.get(recent_temp))
        self.assertIsNotNone(store.get(pinned_temp))
        self.assertEqual(store.count("Work"), 1)
        self.assertEqual(store.count("Personal"), 1)
        return old_temp, pinned_temp

    def test_plaintext_expiry_and_fts_cleanup(self):
        with TemporaryDirectory() as root:
            store = ClipStore(Path(root) / "history.sqlite3")
            try:
                old_temp, pinned = self.exercise_store(store)
                self.assertEqual(
                    store.search_index.search_ids(
                        "old temporary text", "Temporary"
                    ), [],
                )
                self.assertTrue(store.pinned(pinned))
                if store.search_index.enabled:
                    self.assertIsNone(store.conn.execute(
                        "SELECT rowid FROM clipmint_fts WHERE rowid=?",
                        (old_temp,),
                    ).fetchone())
            finally:
                store.close()

    def test_encrypted_expiry_never_decrypts_into_plaintext_sqlite(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "encrypted.sqlite3"
            key = utils.random(SecretBox.KEY_SIZE)
            store = EncryptedClipStore(path, key)
            try:
                self.exercise_store(store)
            finally:
                store.close()
            self.assertNotIn(b"old temporary text", path.read_bytes())

    def test_exact_boundary_and_unpin(self):
        with TemporaryDirectory() as root:
            store = ClipStore(Path(root) / "history.sqlite3")
            try:
                exactly_due = store.add("text", b"exactly due", "exactly due",
                                        "Temporary")
                just_newer = store.add("text", b"newer", "newer", "Temporary")
                age_item(store, exactly_due, timedelta(hours=24))
                age_item(store, just_newer,
                         timedelta(hours=23, minutes=59, seconds=59))
                store.pin(exactly_due, True)
                self.assertEqual(store.expire_temporary_unpinned(now=NOW), 0)
                store.pin(exactly_due, False)
                self.assertEqual(store.expire_temporary_unpinned(now=NOW), 1)
                self.assertIsNone(store.get(exactly_due))
                self.assertIsNotNone(store.get(just_newer))
            finally:
                store.close()

    def test_naive_clock_is_rejected(self):
        with TemporaryDirectory() as root:
            store = ClipStore(Path(root) / "history.sqlite3")
            try:
                with self.assertRaises(ValueError):
                    store.expire_temporary_unpinned(
                        now=datetime(2026, 11, 4, 12, 0)
                    )
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
