"""Privacy, recency and encrypted-history regression tests.

All synthetic values are test-only; no real credentials are used.
The tests assert logical/SQLite cleanup, not SSD forensic erasure guarantees.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import stat
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from nacl.secret import SecretBox
from nacl import utils

from clipmint.store import ClipStore
from clipmint.secure_history import EncryptedClipStore


class HistoryHardeningTests(unittest.TestCase):
    def test_default_database_directory_and_file_modes(self):
        with TemporaryDirectory() as base:
            with patch.dict(os.environ, {"XDG_DATA_HOME": base}):
                home = Path(base) / "clipmint"
                home.mkdir(mode=0o755)
                path = home / "history.sqlite3"
                with patch.object(os, "umask", wraps=os.umask):
                    path.write_bytes(b"")  # existing 0644 file gets repaired
                os.chmod(path, 0o644)
                store = ClipStore()
                try:
                    self.assertEqual(stat.S_IMODE(home.stat().st_mode), 0o700)
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                    self.assertEqual(store.conn.execute(
                        "PRAGMA secure_delete"
                    ).fetchone()[0], 1)
                    self.assertEqual(store.conn.execute(
                        "PRAGMA journal_mode"
                    ).fetchone()[0], "wal")
                finally:
                    store.close()
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(path) + suffix)
                    if sidecar.exists():
                        self.assertEqual(stat.S_IMODE(sidecar.stat().st_mode), 0o600)

    def test_suspicious_history_symlink_is_not_followed(self):
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("platform lacks O_NOFOLLOW")
        with TemporaryDirectory() as root:
            target = Path(root) / "victim"
            target.write_text("untouched")
            alias = Path(root) / "clip-history.sqlite3"
            alias.symlink_to(target)
            with self.assertRaises(OSError):
                ClipStore(alias)
            self.assertEqual(target.read_text(), "untouched")

    def test_a_b_a_reuses_identity_and_preserves_pin_tags_and_favourite(self):
        with TemporaryDirectory() as root:
            store = ClipStore(Path(root) / "history.sqlite3", max_unpinned=2)
            try:
                a = store.add("text", b"Sample A", "Sample A")
                b = store.add("text", b"Sample B", "Sample B")
                store.pin(a, True)
                store.favorite(a, True)
                store.set_tags(a, ["my-notes", "work"])
                before = store.conn.execute(
                    "SELECT touch_seq FROM clips WHERE id=?", (a,)
                ).fetchone()[0]
                again = store.add("text", b"Sample A", "Sample A")
                self.assertEqual(again, a)
                self.assertEqual(store.count("Work"), 2)
                self.assertEqual([x.id for x in store.search()], [a, b])
                self.assertEqual(store.search(sort="Oldest first")[0].id, b)
                self.assertTrue(store.pinned(a))
                self.assertTrue(store.is_favorite(a))
                self.assertEqual(store.tags(a), ["my-notes", "work"])
                self.assertGreater(store.conn.execute(
                    "SELECT touch_seq FROM clips WHERE id=?", (a,)
                ).fetchone()[0], before)
                self.assertEqual([x.id for x in store.search("Sample")], [a, b])
            finally:
                store.close()

    def test_lru_count_limit_and_fingerprint_migration(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "history.sqlite3"
            store = ClipStore(path, max_unpinned=2)
            try:
                a = store.add("text", b"A", "A")
                b = store.add("text", b"B", "B")
                store.conn.execute(
                    "UPDATE clips SET fingerprint=NULL WHERE id=?", (a,)
                )
                store.conn.commit()
                self.assertEqual(store.add("text", b"A", "A"), a)
                c = store.add("text", b"C", "C")
                self.assertIsNone(store.get(b))  # LRU, not lowest ID kept
                self.assertEqual([x.id for x in store.search()], [c, a])
                self.assertEqual(store.count("Work"), 2)
            finally:
                store.close()
            reopened = ClipStore(path)
            try:
                self.assertEqual([x.id for x in reopened.search()], [c, a])
                self.assertEqual(reopened.add("text", b"A", "A"), a)
                self.assertEqual(reopened.count("Work"), 2)
            finally:
                reopened.close()

    def test_encrypted_a_b_a_retains_same_ciphertext_row(self):
        with TemporaryDirectory() as root:
            store = EncryptedClipStore(
                Path(root) / "encrypted.sqlite3",
                utils.random(SecretBox.KEY_SIZE),
            )
            try:
                a = store.add("text", b"SYNTHETIC_A", "A")
                b = store.add("text", b"SYNTHETIC_B", "B")
                store.pin(a, True)
                store.set_tags(a, ["reviewed"])
                original_cipher = store.conn.execute(
                    "SELECT content FROM clips WHERE id=?", (a,)
                ).fetchone()[0]
                self.assertEqual(
                    store.add("text", b"SYNTHETIC_A", "A"), a
                )
                self.assertEqual([x.id for x in store.search()], [a, b])
                self.assertEqual(store.conn.execute(
                    "SELECT content FROM clips WHERE id=?", (a,)
                ).fetchone()[0], original_cipher)
                self.assertEqual(store.tags(a), ["reviewed"])
                self.assertTrue(store.pinned(a))
                self.assertEqual(store.count("Work"), 2)
                store.conn.execute(
                    "UPDATE clips SET fingerprint=NULL WHERE id=?", (a,)
                )
                store.conn.commit()
            finally:
                store.close()
            # Legacy fingerprint backfill runs once on reopening the keyring
            # and no longer re-decrypts old rows for every new clipboard copy.
            store = EncryptedClipStore(store.path, store._dedup_key)
            try:
                self.assertIsNotNone(store.conn.execute(
                    "SELECT fingerprint FROM clips WHERE id=?", (a,)
                ).fetchone()[0])
                with patch.object(store, "_open", wraps=store._open) as decrypt:
                    for i in range(10):
                        store.add("text", f"UNIQUE_{i}".encode(), f"Unique {i}")
                    self.assertEqual(decrypt.call_count, 0)
                self.assertEqual(store.add("text", b"SYNTHETIC_A", "A"), a)
            finally:
                store.close()

    def test_plain_to_encrypted_migration_preserves_last_used_order(self):
        with TemporaryDirectory() as root:
            legacy = ClipStore(Path(root) / "history.sqlite3")
            secure = None
            try:
                a = legacy.add("text", b"First", "First")
                b = legacy.add("text", b"Second", "Second")
                self.assertEqual(legacy.add("text", b"First", "First"), a)
                self.assertEqual([x.id for x in legacy.search()], [a, b])
                key = utils.random(SecretBox.KEY_SIZE)
                secure = EncryptedClipStore.migrate_legacy(
                    legacy, Path(root) / "secure-history.sqlite3", key,
                )
                self.assertEqual([x.id for x in secure.search()], [a, b])
                self.assertEqual(secure.get(a), ("text", b"First"))
                self.assertEqual(secure.conn.execute(
                    "SELECT COUNT(*) FROM clips WHERE fingerprint IS NULL"
                ).fetchone()[0], 0)
                self.assertEqual(secure.add("text", b"First", "First"), a)
            finally:
                if secure is not None:
                    secure.close()
                legacy.close()

    def test_corrupt_legacy_encrypted_entry_is_isolated(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "old-encrypted.sqlite3"
            key = utils.random(SecretBox.KEY_SIZE)
            store = EncryptedClipStore(path, key)
            try:
                healthy = store.add("text", b"Healthy item", "Healthy")
                damaged = store.add("text", b"Corruptible item", "Corruptible")
                store.conn.execute(
                    "UPDATE clips SET content=?,fingerprint=NULL WHERE id=?",
                    (sqlite3.Binary(b"synthetic-corrupt-ciphertext"), damaged)
                )
                store.conn.commit()
            finally:
                store.close()
            store = EncryptedClipStore(path, key)
            try:
                self.assertIn(damaged, store.corrupt_row_ids)
                self.assertEqual([item.id for item in store.search()], [healthy])
                self.assertEqual(store.get(healthy), ("text", b"Healthy item"))
                new_id = store.add("text", b"New healthy", "New healthy")
                self.assertEqual([item.id for item in store.search()],
                                 [new_id, healthy])
                self.assertEqual(store.conn.execute(
                    "SELECT COUNT(*) FROM clips"
                ).fetchone()[0], 3)
                # The quarantined row remains encrypted/opaque in the DB,
                # rather than being silently deleted.
                self.assertIsNotNone(store.conn.execute(
                    "SELECT content FROM clips WHERE id=?", (damaged,)
                ).fetchone())
            finally:
                store.close()

    def test_encrypted_oldest_first_uses_last_copy_not_original_id(self):
        with TemporaryDirectory() as root:
            store = EncryptedClipStore(
                Path(root) / "secure.sqlite3",
                utils.random(SecretBox.KEY_SIZE),
            )
            try:
                a = store.add("text", b"First", "First")
                b = store.add("text", b"Second", "Second")
                self.assertEqual(store.add("text", b"First", "First"), a)
                self.assertEqual([x.id for x in store.search()], [a, b])
                self.assertEqual(
                    [x.id for x in store.search(sort="Oldest first")], [b, a]
                )
            finally:
                store.close()

    def test_delete_checkpoint_and_explicit_compaction(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "history.sqlite3"
            store = ClipStore(path)
            try:
                marker = b"DO_NOT_KEEP_SYNTHETIC_MARKER_ABC_789"
                ident = store.add("text", marker, marker.decode())
                self.assertGreater(store.conn.execute(
                    "SELECT COUNT(*) FROM clipmint_fts"
                ).fetchone()[0], 0)
                store.delete(ident)
                self.assertIsNone(store.get(ident))
                store.compact_history()
                self.assertEqual(store.conn.execute(
                    "SELECT COUNT(*) FROM clipmint_fts"
                ).fetchone()[0], 0)
            finally:
                store.close()
            for candidate in (path, Path(str(path) + "-wal")):
                if candidate.exists():
                    self.assertNotIn(marker, candidate.read_bytes())


if __name__ == "__main__":
    unittest.main()
