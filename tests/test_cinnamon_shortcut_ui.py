"""Qt UI checks for explicit global hotkey takeover and read-only audit.

All OS calls are mocked. These tests must never modify Cinnamon settings.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox, QGroupBox, QKeySequenceEdit

from clipmint.app import ClipMintWindow
from clipmint.cinnamon_hotkey import ShortcutSetupError


class GlobalShortcutUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _window(self, root):
        os.environ["XDG_DATA_HOME"] = root
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, root)
        return ClipMintWindow()

    def test_cinnamon_and_window_shortcuts_share_one_settings_section(self):
        with TemporaryDirectory() as root:
            prior = os.environ.get("XDG_DATA_HOME")
            window = None
            try:
                window = self._window(root)
                sections = [
                    g for g in window.findChildren(QGroupBox)
                    if g.title() == "Keyboard shortcuts"
                ]
                self.assertEqual(len(sections), 1)
                section = sections[0]
                for widget in (
                    window.global_popup_hotkey,
                    window.global_screenshot_hotkey,
                    window.global_record_hotkey,
                    *window.shortcut_editors.values(),
                ):
                    self.assertTrue(section.isAncestorOf(widget))
                self.assertGreaterEqual(
                    len(section.findChildren(QKeySequenceEdit)), 8
                )
            finally:
                if window is not None:
                    window.poller.stop()
                    window._vault_lock_timer.stop()
                    window.store.close()
                    window.screenshot_notice.hide()
                    window.close()
                if prior is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = prior

    def test_user_approved_takeover_has_explicit_second_registration(self):
        with TemporaryDirectory() as root:
            prior = os.environ.get("XDG_DATA_HOME")
            window = None
            try:
                window = self._window(root)
                with patch("clipmint.hotkey_popup_controller.install_shortcut", side_effect=[
                    ShortcutSetupError(
                        "Cinnamon's built-in screenshot action already uses this "
                        "combination. Explicit permission is needed before ClipMint "
                        "can replace it."),
                    "<Primary><Shift>s",
                ]) as installer, patch.object(
                    QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
                ):
                    window.register_cinnamon_screenshot_hotkey()
                self.assertEqual(installer.call_count, 2)
                self.assertNotIn("take_over_screenshot",
                                 installer.call_args_list[0].kwargs)
                self.assertTrue(
                    installer.call_args_list[1].kwargs["take_over_screenshot"]
                )
                self.assertIn("--screenshot-area",
                              installer.call_args_list[1].args[0])
                self.assertEqual(str(
                    window.settings.value("capture/global_shortcut")), "Ctrl+Shift+S")
            finally:
                if window is not None:
                    window.poller.stop()
                    window._vault_lock_timer.stop()
                    window.store.close()
                    window.close()
                if prior is None: os.environ.pop("XDG_DATA_HOME", None)
                else: os.environ["XDG_DATA_HOME"] = prior

    def test_denied_takeover_does_not_register_or_edit_setting(self):
        with TemporaryDirectory() as root:
            prior = os.environ.get("XDG_DATA_HOME")
            window = None
            try:
                window = self._window(root)
                with patch("clipmint.hotkey_popup_controller.install_shortcut", side_effect=[
                    ShortcutSetupError("Explicit permission is needed")
                ]) as installer, patch.object(
                    QMessageBox, "question", return_value=QMessageBox.StandardButton.No
                ):
                    window.register_cinnamon_screenshot_hotkey()
                installer.assert_called_once()
            finally:
                if window is not None:
                    window.poller.stop()
                    window._vault_lock_timer.stop()
                    window.store.close()
                    window.close()
                if prior is None: os.environ.pop("XDG_DATA_HOME", None)
                else: os.environ["XDG_DATA_HOME"] = prior

    def test_global_recorder_and_ownership_report(self):
        with TemporaryDirectory() as root:
            prior = os.environ.get("XDG_DATA_HOME")
            window = None
            try:
                window = self._window(root)
                with patch("clipmint.hotkey_popup_controller.install_shortcut",
                           return_value="<Primary><Shift>r") as installer:
                    window.register_cinnamon_recording_hotkey()
                self.assertIn("--record-area", installer.call_args.args[0])
                self.assertEqual(installer.call_args.args[1], "Ctrl+Shift+R")
                with patch("clipmint.hotkey_popup_controller.shortcut_conflicts",
                           side_effect=lambda seq: [{
                               "source": "custom", "command":
                               window._clipmint_launcher_command(
                                   "--record-area" if seq == "Ctrl+Shift+R"
                                   else "--screenshot-area" if seq == "Ctrl+Shift+S"
                                   else "--toggle"
                               )
                           }]), patch.object(
                               QMessageBox, "information"
                           ) as message:
                    window.audit_global_hotkeys()
                detail = message.call_args.args[2]
                self.assertIn("Screenshot", detail)
                self.assertIn("Recording", detail)
                self.assertIn("Clipboard popup", detail)
                self.assertEqual(detail.count("Assigned to ClipMint"), 3)
            finally:
                if window is not None:
                    window.poller.stop()
                    window._vault_lock_timer.stop()
                    window.store.close()
                    window.close()
                if prior is None: os.environ.pop("XDG_DATA_HOME", None)
                else: os.environ["XDG_DATA_HOME"] = prior


if __name__ == "__main__":
    unittest.main()
