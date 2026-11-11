"""Fast navigation and cold capture-launch regression coverage.

Only synthetic local files are used. No real desktop shortcut is installed,
no screenshot is taken, and the real user's clipboard is not read.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from clipmint import app as app_module
from clipmint.app import ClipMintWindow
from clipmint.window_actions import open_section
from clipmint.kohaku_card import KohakuCardFrame, card_asset_path
from clipmint.recording_controller import RecordingControllerMixin


class FastNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_capture_only_art_is_loaded_only_on_first_actual_display(self):
        asset = card_asset_path()
        self.assertIsNotNone(asset)
        with patch("clipmint.kohaku_card.QPixmap", wraps=QPixmap) as pixmap:
            frame = KohakuCardFrame(defer_image=True)
            self.assertTrue(frame.has_card_art)
            self.assertEqual(frame._pending_asset, asset)
            self.assertFalse(any(
                call.args and call.args[0] == str(asset)
                for call in pixmap.call_args_list
            ))
            frame._load_deferred_art()
            self.assertIsNone(frame._pending_asset)
            self.assertTrue(frame.has_card_art)
            self.assertTrue(any(
                call.args and call.args[0] == str(asset)
                for call in pixmap.call_args_list
            ))
            frame._load_deferred_art()
            self.assertEqual(
                sum(call.args and call.args[0] == str(asset)
                    for call in pixmap.call_args_list), 1
            )

    def test_duplicate_secondary_click_avoids_page_reload(self):
        state = SimpleNamespace(
            _active_section=5,
            pages=Mock(), preview_panel=Mock(), nav_buttons={},
            refresh_library_if_changed=Mock(), refresh=Mock(),
        )
        open_section(state, 5)
        state.pages.setCurrentIndex.assert_not_called()
        state.refresh_library_if_changed.assert_not_called()
        state.refresh.assert_not_called()

    def test_active_gallery_checks_for_changes_without_rebuilding_page(self):
        state = SimpleNamespace(
            _active_section=1,
            pages=Mock(), preview_panel=Mock(), nav_buttons={},
            refresh_library_if_changed=Mock(), refresh=Mock(),
        )
        open_section(state, 1)
        state.pages.setCurrentIndex.assert_not_called()
        state.refresh_library_if_changed.assert_called_once_with("Screenshots")
        state.refresh.assert_not_called()

    def test_clipboard_can_still_explicitly_refresh(self):
        state = SimpleNamespace(
            _active_section=0,
            pages=Mock(), preview_panel=Mock(),
            nav_buttons={"Clipboard": Mock(), "Settings": Mock()},
            refresh_library_if_changed=Mock(), refresh=Mock(),
            _deferred_initial_history_refresh=False,
        )
        open_section(state, 0)
        state.refresh.assert_called_once_with()

    def test_deferred_capture_start_does_not_refresh_archive_on_init(self):
        state = SimpleNamespace(
            _active_section=None,
            pages=Mock(), preview_panel=Mock(),
            nav_buttons={"Clipboard": Mock()},
            _deferred_initial_history_refresh=True,
            refresh=Mock(),
        )
        open_section(state, 0)
        state.refresh.assert_not_called()
        self.assertEqual(state._active_section, 0)

    def test_gallery_navigation_reuses_existing_items_until_dir_changes(self):
        with TemporaryDirectory() as root:
            base = Path(root)
            screenshots, recordings = base / "screenshots", base / "recordings"
            screenshots.mkdir()
            recordings.mkdir()
            prefs = str(base / "prefs.ini")
            with patch.dict(os.environ, {"XDG_DATA_HOME": root}), \
                 patch("clipmint.app.QSettings",
                       side_effect=lambda *_: QSettings(
                           prefs, QSettings.Format.IniFormat)), \
                 patch("clipmint.library_controller.screenshots_dir",
                       return_value=screenshots), \
                 patch("clipmint.library_controller.recordings_dir",
                       return_value=recordings):
                window = ClipMintWindow()
                try:
                    with patch.object(window, "refresh_library",
                                      wraps=window.refresh_library) as reload:
                        window.open_section(1)
                        self.assertEqual(reload.call_count, 1)
                        window.open_section(5)
                        window.open_section(1)
                        self.assertEqual(reload.call_count, 1)
                        # An added file changes the directory stamp.
                        (screenshots / "fresh.png").write_bytes(b"not valid png")
                        window.open_section(5)
                        window.open_section(1)
                        self.assertEqual(reload.call_count, 2)
                        # While the gallery is already active, a click still
                        # detects new files without recreating the page.
                        (screenshots / "same-page-new.png").write_bytes(b"fixture")
                        window.open_section(1)
                        self.assertEqual(reload.call_count, 3)
                        # User-controlled Refresh must bypass the stamp cache.
                        window.refresh_library("Screenshots")
                        self.assertEqual(reload.call_count, 4)
                finally:
                    window._closing = True
                    window._hidden_clipboard_timer.stop()
                    window.poller.stop()
                    window.store.close()
                    window.close()

    def test_recording_controls_do_not_wait_after_area_release(self):
        selector = SimpleNamespace(
            pixel_scale=(1.0, 1.0),
            screen_rect=SimpleNamespace(topLeft=lambda: object()),
        )
        state = SimpleNamespace(
            selector=selector, capture_rect=None,
            capture_scale=None, capture_origin=None,
            clear_selection=Mock(), show_recorder=Mock(),
        )
        callbacks = []
        with patch("clipmint.recording_controller.QTimer.singleShot",
                   side_effect=lambda delay, cb: callbacks.append((delay, cb))):
            RecordingControllerMixin.start_video(state, "selection", None)
        self.assertEqual([ms for ms, _ in callbacks], [0, 0])
        self.assertEqual(state.capture_rect, "selection")
        callbacks[-1][1]()
        state.show_recorder.assert_called_once_with()

    def test_cold_recording_shortcut_never_reveals_archive(self):
        for command, callback in (
            ("--record-area", "choose_recording"),
            ("--screenshot-area", "choose_screenshot"),
        ):
            with self.subTest(command=command):
                window = Mock()
                instance = Mock()
                calls = []
                with patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11"}), \
                     patch("clipmint.app.sys.argv", ["clipmint", command]), \
                     patch("clipmint.app.QApplication") as qt, \
                     patch("clipmint.app.send_command", return_value=False), \
                     patch("clipmint.app.InstanceServer", return_value=instance), \
                     patch("clipmint.app.ClipMintWindow", return_value=window) as ctor, \
                     patch("clipmint.app.QTimer.singleShot",
                           side_effect=lambda ms, cb: calls.append((ms, cb))):
                    qt.return_value.exec.return_value = 0
                    with self.assertRaises(SystemExit):
                        app_module.main()
                ctor.assert_called_once_with(fast_capture=True)
                window.show.assert_not_called()
                self.assertIn(0, [ms for ms, _ in calls])
                callback_fn = calls[0][1]
                callback_fn()
                getattr(window, callback).assert_called_once()


if __name__ == "__main__":
    unittest.main()
