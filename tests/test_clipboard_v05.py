"""Concealed clipboard, rich MIME, Nemo and OCR behaviour regression tests."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")
from PySide6.QtCore import QMimeData, QByteArray, QUrl, Qt
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication

from clipmint.clipboard_formats import (
    is_concealed, sensitive_text, luhn, from_mime, mime_from_entry,
    bundle_from_bytes, bundle_to_bytes,
)
from clipmint.store import ClipStore, classify
from clipmint.ocr import extract_text
from clipmint.quick_popup import fuzzy_score, paste_to_window
from clipmint.foreground_privacy import blocked_foreground
from clipmint.app import ClipMintWindow


class ClipboardFormatsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_concealed_hint_never_captured(self):
        mime = QMimeData()
        mime.setText("Not for retention")
        mime.setData("x-kde-passwordManagerHint", QByteArray(b"secret"))
        self.assertTrue(is_concealed(mime))
        self.assertIsNone(from_mime(mime))
        mime2 = QMimeData()
        mime2.setText("other secret")
        mime2.setData("application/x-keepassxc-private", b"1")
        self.assertIsNone(from_mime(mime2))

    def test_sensitive_key_cards_patterns(self):
        self.assertTrue(luhn("4111 1111 1111 1111"))  # test-only card
        self.assertTrue(sensitive_text("4111 1111 1111 1111"))
        self.assertTrue(sensitive_text("Authorization: Bearer abc"))
        self.assertTrue(sensitive_text("-----BEGIN PRIVATE KEY-----"))
        self.assertFalse(sensitive_text("Just ordinary clipped text"))

    def test_rich_html_roundtrip_and_legacy_schema(self):
        with TemporaryDirectory() as root:
            store = ClipStore(Path(root) / "store.db")
            try:
                mime = QMimeData()
                mime.setText("A bold title")
                mime.setHtml("<b>A bold title</b>")
                captured = from_mime(mime)
                self.assertEqual(captured.kind, "text")
                self.assertIn("text/html", captured.formats)
                clip_id = store.add(captured.kind, captured.content,
                                    captured.preview, formats=captured.formats)
                restored = mime_from_entry(captured.kind, store.get(clip_id)[1],
                                           store.get_formats(clip_id))
                self.assertEqual(restored.text(), "A bold title")
                self.assertIn("<b>A bold title</b>", restored.html())
                self.assertEqual(bundle_from_bytes(bundle_to_bytes(
                    captured.formats)), captured.formats)
            finally:
                store.close()

    def test_nemo_cut_copy_files_preserved(self):
        with TemporaryDirectory() as root:
            store = ClipStore(Path(root) / "db.sqlite3")
            try:
                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile("/tmp/example.txt")])
                mime.setData("x-special/gnome-copied-files",
                             b"cut\nfile:///tmp/example.txt\n")
                result = from_mime(mime)
                self.assertEqual(result.kind, "files")
                self.assertIn("cut\n", result.content.decode())
                ident = store.add(result.kind, result.content,
                                  result.preview, formats=result.formats)
                self.assertEqual(classify(store.search()[0]), "Files")
                restored = mime_from_entry(*store.get(ident),
                                           store.get_formats(ident))
                self.assertEqual(
                    bytes(restored.data("x-special/gnome-copied-files")),
                    b"cut\nfile:///tmp/example.txt\n"
                )
            finally:
                store.close()

    def test_foreground_blocklist_is_best_effort(self):
        self.assertTrue(blocked_foreground(
            "KeePassXC, Bitwarden", window_lookup=lambda: ("5","keepassxc")
        ))
        self.assertFalse(blocked_foreground(
            "KeePassXC", window_lookup=lambda: (None, "")
        ))

    def test_ocr_backend_uses_stdin_and_never_shell(self):
        png = b"\x89PNG\r\n\x1a\nfake-test-image"
        completed = Mock(returncode=0, stdout=b"Invoice Number 123\n")
        with patch("clipmint.ocr.subprocess.run", return_value=completed) as run, \
             patch("clipmint.ocr.shutil.which", return_value="/usr/bin/tesseract"):
            text = extract_text(png)
            self.assertEqual(text, "Invoice Number 123")
            self.assertEqual(run.call_args.kwargs["input"], png)
            self.assertEqual(run.call_args.args[0],
                             ["/usr/bin/tesseract", "stdin", "stdout", "-l", "eng"])
        with self.assertRaises(ValueError):
            extract_text(b"not png")
        with patch("clipmint.ocr.shutil.which", return_value=None):
            with self.assertRaises(RuntimeError):
                extract_text(png)

    def test_fuzzy_search_and_paste_target(self):
        self.assertGreater(fuzzy_score("invoce", "Invoice number"), 50)
        self.assertFalse(paste_to_window("bad;rm -rf", "", "auto"))

    def test_ocr_copy_creates_saved_text_and_avoids_sensitive_history(self):
        with TemporaryDirectory() as root:
            previous = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = ClipMintWindow()
                window.ocr_recognized("Invoice number 735")
                self.assertEqual(QApplication.clipboard().text(), "Invoice number 735")
                self.assertEqual(window.store.search()[0].preview,
                                 "Invoice number 735")
                previous_count = window.store.count("Work")
                window.ocr_recognized("password: abcdefgh1234")
                self.assertEqual(window.store.count("Work"), previous_count)
            finally:
                if window is not None:
                    window.poller.stop()
                    window.store.close()
                    window.hide()
                if previous is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = previous


if __name__ == "__main__":
    unittest.main()
