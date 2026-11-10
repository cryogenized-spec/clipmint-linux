"""Contracts for the library UI extraction without touching live captures."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from clipmint.app import ClipMintWindow, ImagePreviewLabel
from clipmint.library_controller import LibraryControllerMixin
from clipmint.library_controller import ImagePreviewLabel as LibraryImagePreviewLabel


class LibraryControllerRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_main_window_exports_original_archive_callbacks(self):
        self.assertTrue(issubclass(ClipMintWindow, LibraryControllerMixin))
        for method in (
            "build_library_page", "refresh_library",
            "_paint_screenshot_thumbnails", "preview_saved_screenshot",
            "selected_screenshot_path", "open_selected_screenshot",
            "edit_selected_screenshot", "ocr_selected_screenshot",
            "open_saved_file", "screenshot_context_menu",
        ):
            with self.subTest(method=method):
                self.assertIs(getattr(ClipMintWindow, method),
                              getattr(LibraryControllerMixin, method))
        self.assertIs(ImagePreviewLabel, LibraryImagePreviewLabel)

    def test_selected_screenshot_rejects_missing_and_non_png_files(self):
        with TemporaryDirectory() as root:
            png = Path(root) / "saved.png"
            txt = Path(root) / "not-image.txt"
            png.write_bytes(b"synthetic fixture")
            txt.write_text("test-only", encoding="utf-8")
            path = [png]
            item = SimpleNamespace(data=lambda role: str(path[0]))
            listing = SimpleNamespace(currentItem=lambda: item)
            state = SimpleNamespace(libraries={"Screenshots": listing})
            self.assertEqual(LibraryControllerMixin.selected_screenshot_path(state), png)
            path[0] = txt
            self.assertIsNone(LibraryControllerMixin.selected_screenshot_path(state))
            path[0] = Path(root) / "missing.png"
            self.assertIsNone(LibraryControllerMixin.selected_screenshot_path(state))

    def test_open_saved_file_does_not_open_missing_target(self):
        state = SimpleNamespace(open_path=Mock())
        item = SimpleNamespace(data=lambda role: "/nonexistent/clipmint/missing.mp4")
        LibraryControllerMixin.open_saved_file(state, item)
        state.open_path.assert_not_called()

    def test_stale_thumbnail_batch_never_decodes_image(self):
        listing = Mock()
        state = SimpleNamespace(
            _screenshot_thumbnail_generation=3, libraries={"Screenshots": listing},
        )
        item = SimpleNamespace(listWidget=lambda: listing, setIcon=Mock())
        with patch("clipmint.library_controller.screenshot_thumbnail_icon") as decode:
            LibraryControllerMixin._paint_screenshot_thumbnails(
                state, [(item, Path("/unused/preview.png"))], 2
            )
        decode.assert_not_called()
        item.setIcon.assert_not_called()

    def test_screenshot_actions_reuse_existing_main_window_handlers(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "image.png"
            path.write_bytes(b"fixture")
            state = SimpleNamespace(
                selected_screenshot_path=lambda: path,
                open_path=Mock(), edit_last_screenshot=Mock(),
                start_ocr_file=Mock(), _last_screenshot_path=None,
            )
            LibraryControllerMixin.open_selected_screenshot(state)
            LibraryControllerMixin.edit_selected_screenshot(state)
            LibraryControllerMixin.ocr_selected_screenshot(state)
            state.open_path.assert_called_once_with(path)
            state.edit_last_screenshot.assert_called_once_with()
            state.start_ocr_file.assert_called_once_with(path)
            self.assertEqual(state._last_screenshot_path, path)


if __name__ == "__main__":
    unittest.main()
