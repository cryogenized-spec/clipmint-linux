"""Right-click OCR wiring for both clipboard images and saved screenshots."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ.setdefault("XDG_SESSION_TYPE","x11")

from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication, QMenu
from clipmint.app import ClipMintWindow


def png_data():
    image = QImage(80, 50, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    arr = QByteArray()
    buffer = QBuffer(arr)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(arr)


class ContextOcrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_clipboard_image_context_ocr(self):
        with TemporaryDirectory() as root:
            old = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = ClipMintWindow()
                window.resize(1430, 940)
                window.show()
                self.app.processEvents()
                png = png_data()
                ident = window.store.add("image", png, "Image 80 × 50")
                window.refresh()
                # Headless Qt can block indefinitely inside native menu.exec.
                # Test its connected OCR handler directly; real right-click
                # activation remains a Cinnamon desktop acceptance check.
                with patch.object(window, "start_ocr") as run:
                    window.ocr_history_clip(ident)
                    run.assert_called_once_with(png)
            finally:
                if window:
                    window.poller.stop()
                    window.store.close()
                    window.close()
                if old is None: os.environ.pop("XDG_DATA_HOME", None)
                else: os.environ["XDG_DATA_HOME"] = old

    def test_screenshot_notification_ocr_action(self):
        with TemporaryDirectory() as root:
            old = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = ClipMintWindow()
                path = Path(root) / "sample.png"
                png = png_data()
                path.write_bytes(png)
                window._last_screenshot_path = path
                with patch.object(window, "start_ocr") as run:
                    window.screenshot_notice.ocr_button.click()
                    run.assert_called_once_with(png)
            finally:
                if window:
                    window.poller.stop()
                    window.store.close()
                    window.close()
                if old is None: os.environ.pop("XDG_DATA_HOME", None)
                else: os.environ["XDG_DATA_HOME"] = old


if __name__ == "__main__":
    unittest.main()
