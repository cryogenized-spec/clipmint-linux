"""Encrypted history migration and secrecy regression tests using fake data."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from nacl import utils
from nacl.secret import SecretBox
from clipmint.store import ClipStore
from clipmint.secure_history import EncryptedClipStore, HistorySecurityError


class EncryptedHistoryTests(unittest.TestCase):
    def test_sealed_payload_and_preview_and_formats_are_not_plaintext(self):
        with TemporaryDirectory() as root:
            key = utils.random(SecretBox.KEY_SIZE)
            path = Path(root) / "protected.sqlite3"
            db = EncryptedClipStore(path, key)
            try:
                ident = db.add(
                    "text", b"fake internal document content",
                    "Top Secret Business Preview", "Work",
                    formats={"text/html": b"<strong>fake html secret</strong>"},
                )
                self.assertEqual(db.get(ident), ("text", b"fake internal document content"))
                self.assertIn("Top Secret Business Preview", db.search()[0].preview)
                self.assertEqual(db.get_formats(ident)["text/html"],
                                 b"<strong>fake html secret</strong>")
                self.assertEqual(db.add(
                    "text", b"fake internal document content", "Top Secret Business Preview",
                    "Work", formats={"text/html": b"<strong>fake html secret</strong>"}
                ), ident)
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            finally:
                db.close()
            raw = path.read_bytes()
            for forbidden in (b"fake internal document content",
                              b"Top Secret Business Preview",
                              b"fake html secret"):
                self.assertNotIn(forbidden, raw)
            wrong = EncryptedClipStore(path, utils.random(SecretBox.KEY_SIZE))
            try:
                with self.assertRaises(HistorySecurityError):
                    wrong.get(ident)
            finally:
                wrong.close()

    def test_encrypted_templates_and_tags_do_not_create_plaintext_fts(self):
        with TemporaryDirectory() as root:
            key = utils.random(SecretBox.KEY_SIZE)
            target = Path(root) / "protected.sqlite3"
            secure = EncryptedClipStore(target, key)
            try:
                ident = secure.add("text", b"unique classified evidence body",
                                   "classified summary")
                secure.favorite(ident, True)
                secure.set_tags(ident, ["work"])
                tid = secure.save_template("Dispatch", "Client {{name}} private note")
                self.assertEqual(secure.templates()[0][0], tid)
                self.assertEqual(secure.search("", favorites_only=True)[0].id, ident)
                self.assertEqual(secure.search("", tag="work")[0].id, ident)
                self.assertFalse(secure.search_index.enabled)
                self.assertIsNone(secure.conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='clipmint_fts'"
                ).fetchone())
                secure.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                secure.close()
            raw = target.read_bytes()
            self.assertNotIn(b"Client {{name}} private note", raw)
            self.assertNotIn(b"classified evidence body", raw)
            self.assertNotIn(b"classified summary", raw)

    def test_legacy_migration_keeps_original_and_ids_and_pins(self):
        with TemporaryDirectory() as root:
            old_path = Path(root) / "history.sqlite3"
            legacy = ClipStore(old_path)
            keep = legacy.add("text", b"Private note", "Private note")
            legacy.pin(keep, True)
            legacy.favorite(keep, True)
            legacy.set_tags(keep, ["project"])
            legacy.save_template("Report", "Hello {{customer}}")
            other = legacy.add("image", b"fake image bytes", "Image 20 x 20")
            legacy.add_bin("Clients")
            legacy.add("files", b"copy\nfile:///tmp/x", "client file", "Clients",
                       formats={"x-special/gnome-copied-files": b"copy\nfile:///tmp/x"})
            key = utils.random(SecretBox.KEY_SIZE)
            protected_path = Path(root) / "secure-history.sqlite3"
            secure = EncryptedClipStore.migrate_legacy(legacy, protected_path, key)
            try:
                self.assertTrue(old_path.is_file())
                self.assertEqual(legacy.get(keep)[1], b"Private note")
                self.assertEqual(secure.get(keep)[1], b"Private note")
                self.assertEqual(secure.get(other)[0], "image")
                self.assertTrue(secure.pinned(keep))
                self.assertTrue(secure.is_favorite(keep))
                self.assertEqual(secure.tags(keep), ["project"])
                self.assertEqual(secure.templates()[0][2], "Hello {{customer}}")
                self.assertFalse(secure.search_index.enabled)
                self.assertIn("Clients", secure.bins())
                self.assertTrue(secure.search("client", "Clients"))
                self.assertNotIn(b"Private note", protected_path.read_bytes())
                with self.assertRaises(HistorySecurityError):
                    EncryptedClipStore.migrate_legacy(legacy, protected_path, key)
            finally:
                secure.close()
                legacy.close()


if __name__ == "__main__":
    unittest.main()
