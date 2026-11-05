"""An unrelated copy must never be skipped after ClipMint writes to clipboard."""
import unittest
from PySide6.QtCore import QMimeData
from clipmint.clipboard_guard import OwnClipboardGuard


class OwnClipboardGuardTests(unittest.TestCase):
    def test_own_text_suppressed_only_once(self):
        guard = OwnClipboardGuard()
        guard.note_text("original")
        mime = QMimeData()
        mime.setText("original")
        self.assertTrue(guard.consume(mime))
        self.assertFalse(guard.consume(mime))

    def test_new_copy_not_lost(self):
        guard = OwnClipboardGuard()
        guard.note_text("old")
        mime = QMimeData()
        mime.setText("new")
        self.assertFalse(guard.consume(mime))
        self.assertIsNone(guard.expected)

    def test_image_and_files(self):
        guard = OwnClipboardGuard()
        mime = QMimeData()
        mime.setData("image/png", b"PNG fake")
        guard.note_entry("image", b"PNG fake")
        self.assertTrue(guard.consume(mime))
        file_mime = QMimeData()
        file_mime.setData("x-special/gnome-copied-files", b"cut\nfile:///tmp/a")
        guard.note_entry("files", b"cut\nfile:///tmp/a")
        self.assertTrue(guard.consume(file_mime))
        guard.note_entry("image", b"different")
        self.assertFalse(guard.consume(mime))


if __name__ == "__main__":
    unittest.main()
