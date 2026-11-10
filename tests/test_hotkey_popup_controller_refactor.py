"""Regression contracts for the extracted Cinnamon and quick-popup controller.

Never register real Cinnamon shortcuts or paste into external applications.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from clipmint.app import ClipMintWindow
from clipmint.hotkey_popup_controller import HotkeyPopupControllerMixin


class HotkeyPopupRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_window_preserves_original_hotkey_and_popup_callbacks(self):
        self.assertTrue(issubclass(ClipMintWindow, HotkeyPopupControllerMixin))
        for method in (
            "register_cinnamon_hotkey", "_clipmint_launcher_command",
            "register_cinnamon_screenshot_hotkey",
            "restore_cinnamon_screenshot_hotkey",
            "register_cinnamon_recording_hotkey", "audit_global_hotkeys",
            "toggle_quick_popup", "quick_pick", "_paste_to_target",
        ):
            with self.subTest(method=method):
                self.assertIs(getattr(ClipMintWindow, method),
                              getattr(HotkeyPopupControllerMixin, method))

    def test_missing_entry_cannot_change_clipboard_or_auto_paste(self):
        store = SimpleNamespace(
            get=lambda _clip_id: None, get_formats=Mock(),
            refresh_temporary_copy_time=Mock(),
        )
        state = SimpleNamespace(store=store, settings=Mock())
        with patch("clipmint.hotkey_popup_controller.QApplication") as app, \
             patch("clipmint.hotkey_popup_controller.QTimer") as timer:
            HotkeyPopupControllerMixin.quick_pick(
                state, 99, False, "0x42", "Firefox"
            )
            app.clipboard.assert_not_called()
            timer.singleShot.assert_not_called()
        store.refresh_temporary_copy_time.assert_not_called()

    def test_plain_paste_rejects_non_text_without_clipboard_side_effects(self):
        store = SimpleNamespace(
            get=lambda _clip_id: ("image", b"test-image"),
            refresh_temporary_copy_time=Mock(),
        )
        state = SimpleNamespace(store=store, inform=Mock())
        with patch("clipmint.hotkey_popup_controller.QApplication") as app, \
             patch("clipmint.hotkey_popup_controller.QTimer") as timer:
            HotkeyPopupControllerMixin.quick_pick(
                state, 2, True, "0x42", "Firefox"
            )
            app.clipboard.assert_not_called()
            timer.singleShot.assert_not_called()
        store.refresh_temporary_copy_time.assert_not_called()
        state.inform.assert_called_once()

    def test_auto_paste_setting_false_only_copies_text(self):
        clipboard = QApplication.clipboard()
        old_text = clipboard.text()
        guard = SimpleNamespace(note_text=Mock())
        store = SimpleNamespace(
            get=lambda _clip_id: ("text", b"safe copy fixture"),
            refresh_temporary_copy_time=Mock(),
        )
        settings = SimpleNamespace(value=lambda *args, **kwargs: False)
        state = SimpleNamespace(
            store=store, settings=settings,
            _own_clipboard_guard=guard, _paste_to_target=Mock(),
        )
        try:
            with patch("clipmint.hotkey_popup_controller.QTimer") as timer:
                HotkeyPopupControllerMixin.quick_pick(
                    state, 7, True, "0x42", "Firefox"
                )
                timer.singleShot.assert_not_called()
            self.assertEqual(clipboard.text(), "safe copy fixture")
            guard.note_text.assert_called_once_with("safe copy fixture")
            store.refresh_temporary_copy_time.assert_called_once_with(7)
            state._paste_to_target.assert_not_called()
        finally:
            clipboard.setText(old_text)

    def test_auto_paste_only_schedules_after_user_opt_in(self):
        clipboard = QApplication.clipboard()
        old_text = clipboard.text()
        store = SimpleNamespace(
            get=lambda _clip_id: ("text", b"safe copy fixture"),
            refresh_temporary_copy_time=Mock(),
        )
        state = SimpleNamespace(
            store=store,
            settings=SimpleNamespace(value=lambda *args, **kwargs: True),
            _own_clipboard_guard=SimpleNamespace(note_text=Mock()),
            _paste_to_target=Mock(),
        )
        try:
            with patch("clipmint.hotkey_popup_controller.QTimer") as timer:
                HotkeyPopupControllerMixin.quick_pick(
                    state, 7, True, "0x42", "Firefox"
                )
                timer.singleShot.assert_called_once()
                self.assertEqual(timer.singleShot.call_args.args[0], 150)
                # Scheduling a callback is not evidence that paste occurred.
                state._paste_to_target.assert_not_called()
        finally:
            clipboard.setText(old_text)

    def test_launcher_command_preserves_argument_and_quotes_path(self):
        state = SimpleNamespace()
        with patch("clipmint.hotkey_popup_controller.sys.frozen", False, create=True), \
             patch("clipmint.hotkey_popup_controller.sys.executable",
                   "/tmp/path with space/python"):
            command = HotkeyPopupControllerMixin._clipmint_launcher_command(
                state, "--toggle"
            )
        self.assertIn("'/tmp/path with space/python'", command)
        self.assertTrue(command.endswith(" --toggle"))
        self.assertIn("launcher.py", command)


if __name__ == "__main__":
    unittest.main()
