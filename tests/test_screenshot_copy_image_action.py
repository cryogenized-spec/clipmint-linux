"""Screenshot-gallery Copy image uses original PNG bytes, never thumbnails."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from clipmint.library_controller import LibraryControllerMixin


class ScreenshotCopyImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_copy_image_keeps_full_resolution_and_original_png_bytes(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "saved.png"
            source = QImage(320, 240, QImage.Format.Format_RGB32)
            source.fill(QColor("#C0607C"))
            self.assertTrue(source.save(str(path), "PNG"))
            expected = path.read_bytes()
            guard, inform, error = Mock(), Mock(), Mock()
            state = SimpleNamespace(
                selected_screenshot_path=lambda: path,
                _own_clipboard_guard=guard,
                inform=inform, error=error,
            )
            clipboard = QApplication.clipboard()
            clipboard.setText("earlier text")
            try:
                self.assertTrue(
                    LibraryControllerMixin.copy_selected_screenshot(state)
                )
                mime = clipboard.mimeData()
                self.assertEqual(bytes(mime.data("image/png")), expected)
                self.assertTrue(mime.hasImage())
                self.assertEqual(
                    (mime.imageData().width(), mime.imageData().height()),
                    (320, 240),
                )
                guard.note_entry.assert_called_once_with("image", expected)
                inform.assert_called_once_with("Image copied", path.name)
                error.assert_not_called()
            finally:
                clipboard.clear()

    def test_missing_or_corrupt_file_does_not_replace_clipboard(self):
        with TemporaryDirectory() as temp:
            target = [None]
            guard, inform, error = Mock(), Mock(), Mock()
            state = SimpleNamespace(
                selected_screenshot_path=lambda: target[0],
                _own_clipboard_guard=guard, inform=inform, error=error,
            )
            board = QApplication.clipboard()
            board.setText("preserve me")
            try:
                self.assertFalse(
                    LibraryControllerMixin.copy_selected_screenshot(state)
                )
                target[0] = Path(temp) / "invalid.png"
                target[0].write_bytes(b"not a PNG")
                self.assertFalse(
                    LibraryControllerMixin.copy_selected_screenshot(state)
                )
                self.assertEqual(board.text(), "preserve me")
                guard.note_entry.assert_not_called()
                inform.assert_not_called()
                error.assert_called_once()
            finally:
                board.clear()

    def test_context_menu_selects_right_clicked_image_before_copy(self):
        target = Path("/synthetic/screenshot.png")
        image = SimpleNamespace(data=lambda _role: str(target))
        listing = Mock()
        listing.itemAt.return_value = image
        state = SimpleNamespace(
            libraries={"Screenshots": listing},
            copy_selected_screenshot=Mock(),
            start_ocr_file=Mock(),
            edit_last_screenshot=Mock(),
            _last_screenshot_path=None,
        )
        actions = [object(), object(), object()]
        with patch("clipmint.library_controller.QMenu") as menu_cls:
            menu = menu_cls.return_value
            menu.addAction.side_effect = actions
            menu.exec.return_value = actions[0]
            LibraryControllerMixin.screenshot_context_menu(state, QPoint(4, 6))
            menu.addAction.assert_any_call("Copy image")
            menu.addAction.assert_any_call("OCR · Extract text")
            menu.addAction.assert_any_call("Open in image editor")
        listing.setCurrentItem.assert_called_once_with(image)
        state.copy_selected_screenshot.assert_called_once()
        state.start_ocr_file.assert_not_called()
        state.edit_last_screenshot.assert_not_called()

    def test_existing_ocr_and_edit_menu_actions_remain_functional(self):
        target = Path("/synthetic/screenshot.png")
        image = SimpleNamespace(data=lambda _role: str(target))
        listing = Mock()
        listing.itemAt.return_value = image
        state = SimpleNamespace(
            libraries={"Screenshots": listing},
            copy_selected_screenshot=Mock(),
            start_ocr_file=Mock(),
            edit_last_screenshot=Mock(),
            _last_screenshot_path=None,
        )
        actions = [object(), object(), object()]
        with patch("clipmint.library_controller.QMenu") as menu_cls:
            menu_cls.return_value.addAction.side_effect = actions * 2
            menu_cls.return_value.exec.side_effect = [actions[1], actions[2]]
            LibraryControllerMixin.screenshot_context_menu(state, QPoint(0, 0))
            LibraryControllerMixin.screenshot_context_menu(state, QPoint(0, 0))
        state.start_ocr_file.assert_called_once_with(target)
        state.edit_last_screenshot.assert_called_once()
        self.assertEqual(state._last_screenshot_path, target)
        state.copy_selected_screenshot.assert_not_called()


if __name__ == "__main__":
    unittest.main()
