"""Basic Qt smoke tests without a physical display."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage, QColor
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

    def test_image_preview_switches_between_image_and_text(self):
        with TemporaryDirectory() as temporary:
            original = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = temporary
            window = None
            try:
                window = ClipMintWindow()
                window.show()
                self.app.processEvents()
                window.store.add("text", b"example text", "example text")
                image = QImage(64, 32, QImage.Format.Format_ARGB32)
                image.fill(QColor("#00FF9D"))
                encoded = QByteArray()
                buffer = QBuffer(encoded)
                self.assertTrue(buffer.open(QIODevice.OpenModeFlag.WriteOnly))
                self.assertTrue(image.save(buffer, "PNG"))
                buffer.close()
                image_id = window.store.add("image", bytes(encoded), "Image 64 × 32")
                window.refresh()
                image_item = next(
                    window.history.item(i) for i in range(window.history.count())
                    if window.history.item(i).data(Qt.ItemDataRole.UserRole) == image_id
                )
                window.history.setCurrentItem(image_item)
                self.app.processEvents()
                self.assertIs(window.preview_stack.currentWidget(), window.preview_image_page)
                self.assertEqual(window.preview_dimensions.text(), "64 × 32 pixels")
                self.assertIsNotNone(window.preview_image.pixmap())
                self.assertFalse(window.preview_image.pixmap().isNull())
                text_item = next(
                    window.history.item(i) for i in range(window.history.count())
                    if window.history.item(i) is not image_item
                )
                window.history.setCurrentItem(text_item)
                self.app.processEvents()
                self.assertIs(window.preview_stack.currentWidget(), window.preview_label)
                self.assertIn("example text", window.preview_label.text())
                self.assertIn("Screenshot Area", window.screenshot_button.text())
            finally:
                if window is not None:
                    window.store.close()
                    window.close()
                    window.deleteLater()
                if original is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = original

    def test_dotgothic16_wordmark_renders_without_network(self):
        with TemporaryDirectory() as temporary:
            original = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = temporary
            window = None
            try:
                window = ClipMintWindow()
                window.show()
                self.app.processEvents()
                self.assertEqual(window.wordmark.accessibleName(), "ClipMint")
                self.assertEqual(window.wordmark.word, "CLIPMINT")
                picture = window.wordmark.grab().toImage()
                self.assertFalse(picture.isNull())
                self.assertGreater(picture.width(), 100)
                self.assertGreater(picture.height(), 35)
                if (Path(__file__).resolve().parents[1] / "vendor/fonts/DotGothic16-Regular.ttf").exists():
                    self.assertEqual(window.brand_family, "DotGothic16")
                    self.assertEqual(window.wordmark.display_font.family(), "DotGothic16")
            finally:
                if window is not None:
                    window.store.close()
                    window.close()
                    window.deleteLater()
                if original is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = original

    def test_invalid_image_falls_back_to_message(self):
        with TemporaryDirectory() as temporary:
            original = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = temporary
            window = None
            try:
                window = ClipMintWindow()
                window.store.add("image", b"not a PNG", "Invalid image")
                window.refresh()
                window.history.setCurrentRow(0)
                self.app.processEvents()
                self.assertIs(window.preview_stack.currentWidget(), window.preview_label)
                self.assertEqual(window.preview_label.text(), "Unable to preview this image")
            finally:
                if window is not None:
                    window.store.close()
                    window.close()
                    window.deleteLater()
                if original is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = original


if __name__ == "__main__":
    unittest.main()
