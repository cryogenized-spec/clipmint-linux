"""Contracts for the extracted screenshot lifecycle callbacks."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from clipmint.app import ClipMintWindow
from clipmint.screenshot_capture_controller import ScreenshotCaptureControllerMixin


class ScreenshotCaptureRefactorTests(unittest.TestCase):
    def test_main_window_keeps_all_original_capture_callbacks(self):
        self.assertTrue(issubclass(ClipMintWindow, ScreenshotCaptureControllerMixin))
        for name in (
            "select_area", "begin_selection", "clear_selection",
            "selection_cancelled", "choose_screenshot", "screenshot_full",
            "finish_full_screenshot", "save_screenshot",
            "notify_screenshot_captured", "dismiss_screenshot_notice",
            "edit_last_screenshot", "open_path", "open_folder",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(ClipMintWindow,name),
                              getattr(ScreenshotCaptureControllerMixin,name))

    def test_selection_refuses_when_recorder_is_active(self):
        state=SimpleNamespace(
            selector=None,recorder_window=None,
            recorder=SimpleNamespace(process=object()),inform=Mock(),
        )
        with patch("clipmint.screenshot_capture_controller.QTimer") as timer:
            ScreenshotCaptureControllerMixin.select_area(state,"video")
        state.inform.assert_called_once()
        timer.singleShot.assert_not_called()

    def test_failed_capture_never_copies_pixels_or_notifies(self):
        with TemporaryDirectory() as root:
            pixmap=SimpleNamespace(isNull=lambda: True,save=Mock())
            state=SimpleNamespace(
                _capture_restore_main=False,clear_selection=Mock(),
                show_window=Mock(),error=Mock(),
                notify_screenshot_captured=Mock(),refresh_library=Mock(),
            )
            with patch("clipmint.screenshot_capture_controller.screenshots_dir",
                       return_value=Path(root)), \
                 patch("clipmint.screenshot_capture_controller.QTimer") as timer, \
                 patch("clipmint.screenshot_capture_controller.QApplication") as app:
                ScreenshotCaptureControllerMixin.save_screenshot(state,None,pixmap)
                app.clipboard.assert_not_called()
                timer.singleShot.assert_called_once()
            state.notify_screenshot_captured.assert_not_called()
            state.refresh_library.assert_not_called()
            state.error.assert_called_once()
            pixmap.save.assert_not_called()

    def test_successful_capture_hides_main_app_and_copies_image(self):
        with TemporaryDirectory() as root:
            image=object()
            pixmap=SimpleNamespace(
                isNull=lambda: False,save=Mock(return_value=True),
                toImage=lambda: image,
            )
            state=SimpleNamespace(
                _capture_restore_main=True, clear_selection=Mock(),
                hide=Mock(),show_window=Mock(),
                notify_screenshot_captured=Mock(),refresh_library=Mock(),
            )
            with patch("clipmint.screenshot_capture_controller.screenshots_dir",
                       return_value=Path(root)), \
                 patch("clipmint.screenshot_capture_controller.QTimer"), \
                 patch("clipmint.screenshot_capture_controller.QApplication") as app:
                ScreenshotCaptureControllerMixin.save_screenshot(state,None,pixmap)
                app.clipboard.return_value.setImage.assert_called_once_with(image)
            state.hide.assert_called_once()
            state.show_window.assert_not_called()
            self.assertFalse(state._capture_restore_main)
            state.notify_screenshot_captured.assert_called_once()
            state.refresh_library.assert_called_once()

    def test_cancelled_selection_only_restores_previous_foreground(self):
        state=SimpleNamespace(
            _capture_restore_main=False,clear_selection=Mock(),show_window=Mock(),
        )
        with patch("clipmint.screenshot_capture_controller.QTimer") as timer:
            ScreenshotCaptureControllerMixin.selection_cancelled(state)
            state.show_window.assert_not_called()
            state._capture_restore_main=True
            ScreenshotCaptureControllerMixin.selection_cancelled(state)
            state.show_window.assert_called_once()
            self.assertFalse(state._capture_restore_main)
            self.assertEqual(timer.singleShot.call_count,2)


if __name__ == "__main__":
    unittest.main()
