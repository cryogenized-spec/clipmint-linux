"""Screenshot archive gallery and preview regression tests (synthetic PNGs only)."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from clipmint.app import ClipMintWindow
from clipmint.screenshot_gallery import read_screenshot, screenshot_thumbnail_icon


def create_png(path: Path, width: int, height: int) -> None:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#C0607C"))
    assert image.save(str(path), "PNG")


class ScreenshotGalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_reader_bounded_and_invalid_images_handled(self):
        with TemporaryDirectory() as root:
            folder = Path(root)
            good = folder / "good.png"
            create_png(good, 640, 360)
            result = read_screenshot(good, QSize(200, 120))
            self.assertIsNotNone(result)
            scaled, full = result
            self.assertEqual((full.width(), full.height()), (640, 360))
            self.assertLessEqual(scaled.width(), 200)
            self.assertLessEqual(scaled.height(), 120)
            self.assertIsNotNone(screenshot_thumbnail_icon(good))
            invalid = folder / "broken.png"
            invalid.write_bytes(b"not a real PNG")
            self.assertIsNone(read_screenshot(invalid, QSize(200, 120)))
            self.assertIsNone(screenshot_thumbnail_icon(invalid))

    def test_gallery_has_thumbnails_previews_actions_and_selection_retention(self):
        with TemporaryDirectory() as root:
            workspace = Path(root)
            screenshots = workspace / "shots"
            recordings = workspace / "recordings"
            screenshots.mkdir()
            recordings.mkdir()
            first = screenshots / "first.png"
            second = screenshots / "second.png"
            create_png(first, 640, 360)
            create_png(second, 320, 240)
            previous = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = str(workspace)
            window = None
            try:
                with (
                    patch("clipmint.app.screenshots_dir", return_value=screenshots),
                    patch("clipmint.app.recordings_dir", return_value=recordings),
                ):
                    window = ClipMintWindow()
                    window.resize(1380, 900)
                    window.show()
                    self.app.processEvents()
                    window.open_section(1)
                    self.app.processEvents()
                    listing = window.libraries["Screenshots"]
                    self.assertEqual(listing.count(), 2)
                    self.assertEqual(listing.objectName(), "screenshotGallery")
                    self.assertIn("2 saved screenshots", window.screenshot_count.text())
                    self.assertFalse(listing.item(0).icon().isNull())
                    self.assertIsNotNone(window.screenshot_preview_image._original)
                    self.assertFalse(window.screenshot_preview_image._original.isNull())
                    self.assertIn("px", window.screenshot_details.text())
                    self.assertIn("capturePreviewPane", window.styleSheet())

                    chosen = next(
                        listing.item(i) for i in range(listing.count())
                        if listing.item(i).data(Qt.ItemDataRole.UserRole) == str(second)
                    )
                    listing.setCurrentItem(chosen)
                    self.app.processEvents()
                    self.assertIn("320 × 240 px", window.screenshot_details.text())
                    self.assertEqual(window.selected_screenshot_path(), second)

                    with patch.object(window, "open_path") as opened:
                        window.open_selected_screenshot()
                        opened.assert_called_once_with(second)
                    with patch.object(window, "start_ocr_file") as ocr:
                        window.ocr_selected_screenshot()
                        ocr.assert_called_once_with(second)
                    with patch.object(window, "edit_last_screenshot") as editor:
                        window.edit_selected_screenshot()
                        editor.assert_called_once_with()
                        self.assertEqual(window._last_screenshot_path, second)

                    window.refresh_library("Screenshots")
                    self.assertEqual(window.selected_screenshot_path(), second)
                    self.assertIn("320 × 240", window.screenshot_details.text())

                    # The pre-existing recordings list still operates independently.
                    (recordings / "sample.mp4").write_bytes(b"test-only")
                    window.open_section(2)
                    self.assertEqual(window.libraries["Recordings"].count(), 1)
            finally:
                if window is not None:
                    window.poller.stop()
                    window.store.close()
                    window.close()
                if previous is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = previous


if __name__ == "__main__":
    unittest.main()
