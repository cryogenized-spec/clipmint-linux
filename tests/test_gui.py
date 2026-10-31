"""Basic Qt smoke tests without a physical display."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")
from PySide6.QtWidgets import QApplication
from clipmint.app import ClipMintWindow


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_window_and_clipboard_menu(self):
        with TemporaryDirectory() as temporary:
            original = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = temporary
            try:
                window = ClipMintWindow()
                window.store.add("text", b"clipmint example", "clipmint example")
                window.refresh()
                self.assertEqual(window.history.count(), 1)
                window.copy_clip(window.history.item(0))
                self.assertEqual(QApplication.clipboard().text(), "clipmint example")
                window.store.close()
                window.deleteLater()
            finally:
                if original is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = original


if __name__ == "__main__":
    unittest.main()
