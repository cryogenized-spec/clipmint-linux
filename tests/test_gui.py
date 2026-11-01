"""Basic Qt smoke tests without a physical display."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from clipmint.recording_ui import SaveClipDialog
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


    def test_recording_dialog_keyboard_save_and_discard(self):
        with TemporaryDirectory() as temp:
            sample = Path(temp) / "recording.mp4"
            sample.write_bytes(b"sample-video")
            dialog = SaveClipDialog(sample, "00:00:03", "High")
            dialog.show()
            self.app.processEvents()
            self.assertTrue(dialog.yes_button.isDefault())
            QTest.keyClick(dialog, Qt.Key.Key_Return)
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
            dialog.close()

            dialog2 = SaveClipDialog(sample, "00:00:03", "High")
            dialog2.show()
            self.app.processEvents()
            QTest.keyClick(dialog2, Qt.Key.Key_Right)
            self.assertTrue(dialog2.no_button.isDefault())
            QTest.keyClick(dialog2, Qt.Key.Key_Return)
            self.assertEqual(dialog2.result(), QDialog.DialogCode.Rejected)
            dialog2.close()


if __name__ == "__main__":
    unittest.main()
