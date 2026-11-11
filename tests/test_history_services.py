"""Schema and retention service boundaries preserve data and consent."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from clipmint.store import ClipStore
from clipmint.history_retention import HistoryRetentionService
from clipmint.secure_history import EncryptedClipStore
from nacl.secret import SecretBox
from nacl.utils import random


class HistoryServicesTests(unittest.TestCase):
    def test_store_injects_same_connection_and_index(self):
        with TemporaryDirectory() as folder:
            store = ClipStore(Path(folder) / "plain.sqlite3")
            try:
                self.assertIsInstance(store._retention, HistoryRetentionService)
                self.assertIs(store._retention.conn, store.conn)
                self.assertIs(store._retention.search_index, store.search_index)
                self.assertEqual(store.max_total_bytes, None)
            finally:
                store.close()

    def test_legacy_mime_migration_is_repeatable_and_preserves_data(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "legacy.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute("""
                    CREATE TABLE clips (
                        id INTEGER PRIMARY KEY,
                        kind TEXT NOT NULL CHECK(kind IN ('text','image')),
                        content BLOB NOT NULL,
                        preview TEXT NOT NULL,
                        pinned INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00Z'
                    )
                """)
                connection.execute(
                    "INSERT INTO clips(id, kind, content, preview, pinned) "
                    "VALUES(29, 'text', ?, 'historic entry', 1)",
                    (b"historic payload",),
                )
            for _ in range(2):
                store = ClipStore(path)
                try:
                    self.assertEqual(store.get(29), ("text", b"historic payload"))
                    self.assertTrue(store.pinned(29))
                    self.assertEqual(store.search("historic")[0].id, 29)
                    self.assertIn("files", store.conn.execute(
                        "SELECT sql FROM sqlite_master WHERE name='clips'"
                    ).fetchone()[0])
                finally:
                    store.close()

    def test_opt_in_byte_cap_keeps_pins_and_avoids_extra_connections(self):
        with TemporaryDirectory() as folder:
            store = ClipStore(Path(folder) / "plain.sqlite3")
            try:
                ident = store.add("image", b"X" * 220, "Pinned image")
                store.pin(ident, True)
                store.max_total_bytes = 64
                self.assertEqual(store.prune_storage_bytes(), 0)
                self.assertIsNotNone(store.get(ident))
                self.assertIs(store._retention.conn, store.conn)
            finally:
                store.close()

    def test_temporary_expiry_protects_pins_and_other_bins(self):
        with TemporaryDirectory() as folder:
            store = ClipStore(Path(folder) / "plain.sqlite3")
            try:
                old = store.add("text", b"old temporary", "Old", "Temporary")
                keep = store.add("text", b"old pinned", "Pinned", "Temporary")
                work = store.add("text", b"old work", "Work", "Work")
                store.pin(keep, True)
                timestamp = (datetime.now(timezone.utc) -
                             timedelta(days=2)).isoformat()
                store.conn.execute(
                    "UPDATE clips SET created_at=? WHERE id IN (?, ?, ?)",
                    (timestamp, old, keep, work),
                )
                store.conn.commit()
                removed = []
                self.assertEqual(
                    store.expire_temporary_unpinned(deleted_ids=removed), 1
                )
                self.assertEqual(removed, [old])
                self.assertIsNone(store.get(old))
                self.assertIsNotNone(store.get(keep))
                self.assertIsNotNone(store.get(work))
            finally:
                store.close()

    def test_encrypted_history_disables_fts_even_with_shared_retention_service(self):
        with TemporaryDirectory() as folder:
            store = EncryptedClipStore(
                Path(folder) / "encrypted.sqlite3", random(SecretBox.KEY_SIZE)
            )
            try:
                self.assertIs(store._retention.conn, store.conn)
                self.assertFalse(store._retention.search_index.enabled)
                self.assertIsNone(store.conn.execute(
                    "SELECT name FROM sqlite_master WHERE name='clipmint_fts'"
                ).fetchone())
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
