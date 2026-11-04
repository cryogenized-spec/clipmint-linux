"""Regression coverage for Codex privacy and responsiveness review findings.

Only fabricated text and ephemeral Qt/SQLite fixtures are used.
"""
from __future__ import annotations

import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from nacl import utils
from nacl.secret import SecretBox
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from clipmint.app import ClipMintWindow
from clipmint.clipboard_formats import from_mime, sensitive_payload, sensitive_text
from clipmint.secure_history import EncryptedClipStore
from clipmint.smart_types import classify_smart
from clipmint.store import ClipStore


class CodexAutosortRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_oversized_text_cannot_bypass_privacy_gate(self):
        # The classifier's normal 256 KiB cap must not become a secret bypass.
        prefix = "Normal workshop notes; copied as one text document.\n" * 6100
        self.assertGreater(len(prefix), 262144)
        payloads = (
            prefix + "MY_REFRESH_TOKEN=synthetic_value_12345",
            prefix + "IBAN: DE89370400440532013000",
            prefix + "GITHUB_CLIENT_SECRET=FAKE_secret_12345678",
        )
        with TemporaryDirectory() as root:
            store = ClipStore(Path(root) / "test.sqlite3")
            try:
                for item in payloads:
                    with self.subTest(item=item[-45:]):
                        self.assertTrue(sensitive_text(item))
                        self.assertIsNone(store.add(
                            "text", item.encode(), item[:90], "Work"
                        ))
                self.assertEqual(store.count("Work"), 0)
            finally:
                store.close()

    def test_image_and_file_mime_alternatives_are_not_persisted(self):
        with TemporaryDirectory() as root:
            stores = [
                ClipStore(Path(root) / "ordinary.sqlite3"),
                EncryptedClipStore(Path(root) / "encrypted.sqlite3",
                                   utils.random(SecretBox.KEY_SIZE)),
            ]
            try:
                sensitive_alternates = (
                    ("image", b"fakePNG", {
                        "text/html": b"<span>MY_REFRESH_TOKEN=FAKE_123456</span>"
                    }),
                    ("files", b"file:///tmp/synthetic.txt", {
                        "text/plain": b"CLIENT_SECRET=fakeOnly123456"
                    }),
                )
                for store in stores:
                    for kind, content, formats in sensitive_alternates:
                        with self.subTest(store=type(store).__name__, kind=kind):
                            self.assertTrue(sensitive_payload(kind, content, formats))
                            self.assertIsNone(store.add(
                                kind, content, "safe preview", "Work", formats=formats,
                            ))
                    self.assertEqual(store.count("Work"), 0)
            finally:
                for store in stores:
                    store.close()
        clipboard = QMimeData()
        clipboard.setText("MY_REFRESH_TOKEN=fakeOnly12345")
        clipboard.setHtml("<b>Normal formatted title</b>")
        self.assertIsNone(from_mime(clipboard, png=b"fakePNG"))
        alternate = QMimeData()
        alternate.setText("Normal preview")
        alternate.setHtml("<b>GITHUB_CLIENT_SECRET=fakeOnly12345</b>")
        self.assertIsNone(from_mime(alternate, png=b"fakePNG"))

    def test_deep_json_is_handled_without_exception(self):
        nested = "[" * 10000 + "0" + "]" * 10000
        self.assertIn(classify_smart("text", nested), ("json", "plain-text"))
        self.assertFalse(sensitive_text(nested))

    def test_iso_date_precedes_generic_phone_guess(self):
        self.assertEqual(classify_smart("text", "2026-11-04"), "calendar-dates")
        self.assertEqual(classify_smart("text", "+27 82 123 4567"), "phone")

    def test_whitespace_attacks_do_not_stall_the_event_loop(self):
        for sample in ("<node" + " " * 16000 + "!",
                       "\n" * 16000 + "not-a-key",
                       "<svg" + " " * 16000 + "!"):
            with self.subTest(name=sample[:8]):
                start = time.perf_counter()
                sensitive_text(sample)
                elapsed = time.perf_counter() - start
                self.assertLess(
                    elapsed, 1.8,
                    f"Untrusted input stalled content screening ({elapsed:.2f}s)"
                )

    def test_replacement_copy_invalidates_old_clipboard_expiry(self):
        with TemporaryDirectory() as root:
            previous = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = ClipMintWindow()
                window.vault.create("synthetic-test-passphrase-123")
                window.vault.add("Synthetic OTP", "834261", "Secret")
                window.refresh_vault()
                window.vault_items.setCurrentRow(0)
                clipboard = QApplication.clipboard()
                clipboard.setText("834261")
                self.app.processEvents()
                old_generation = window._sensitive_clipboard_token
                self.assertGreater(old_generation, 0)

                # The same bytes are copied afresh from the Vault. The old
                # 30-second expiry must not clear this newer clipboard copy.
                window.copy_vault_value()
                self.app.processEvents()
                self.assertGreater(window._sensitive_clipboard_token,
                                   old_generation)
                self.assertEqual(clipboard.text(), "834261")
                window.expire_sensitive_clipboard(old_generation, "834261")
                self.assertEqual(clipboard.text(), "834261")
                window.expire_vault_clipboard(window._vault_clipboard_token)
                self.assertEqual(clipboard.text(), "")
            finally:
                if window is not None:
                    window.poller.stop()
                    window._vault_lock_timer.stop()
                    window.store.close()
                    window.close()
                if previous is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = previous


if __name__ == "__main__":
    unittest.main()
