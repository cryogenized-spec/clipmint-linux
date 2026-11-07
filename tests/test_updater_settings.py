"""ClipMint updater UI does not install elevated packages or block clipboard UI."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from clipmint.app import ClipMintWindow


class UpdateSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = TemporaryDirectory()
        self.previous = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = self.folder.name
        preferences = str(Path(self.folder.name) / "updater-settings.ini")
        with patch("clipmint.app.QSettings",
                   side_effect=lambda *_args: QSettings(
                       preferences, QSettings.Format.IniFormat
                   )):
            self.window = ClipMintWindow()

    def tearDown(self):
        w = self.window
        w._auto_update_timer.stop()
        w._hidden_clipboard_timer.stop()
        w.poller.stop()
        w._vault_lock_timer.stop()
        w._temporary_expiry_timer.stop()
        w._closing = True
        w.screenshot_notice.hide()
        if not w.store.closed:
            w.store.close()
        w.hide()
        w.deleteLater()
        self.app.processEvents()
        if self.previous is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.previous
        self.folder.cleanup()

    def test_preview_check_is_configurable_and_off_stops_network(self):
        w = self.window
        self.assertFalse(w.auto_update_toggle.isChecked())
        with patch.object(w, "check_for_updates") as check:
            w._auto_check_updates()
            check.assert_not_called()
            w.auto_update_toggle.setChecked(False)
            self.assertFalse(
                w.settings.value("updates/automatic", True, type=bool)
            )
            w._auto_check_updates()
            check.assert_not_called()
            w.auto_update_toggle.setChecked(True)
            check.assert_called_once_with(manual=False)

    def test_download_notification_never_installs_without_user_action(self):
        w = self.window
        with TemporaryDirectory() as root:
            path = Path(root) / "clipmint_0.6.0~preview1.301.1_amd64.deb"
            path.write_bytes(b"test fixture only")
            with patch.object(w, "open_path") as open_package:
                w._on_update_result("0.6.0~preview1.301.1", str(path), "")
                self.assertTrue(w.install_update_button.isEnabled())
                self.assertIn("Verified update", w.update_status.text())
                open_package.assert_not_called()
                w.open_verified_update()
                open_package.assert_called_once_with(path)

    def test_network_protocol_error_does_not_disable_check_button_forever(self):
        w = self.window
        def run_synchronously(*_args, **kwargs):
            class FakeThread:
                def start(self):
                    kwargs["target"]()
            return FakeThread()
        with patch("clipmint.app.check_for_preview_update",
                   side_effect=RuntimeError("truncated update stream")), \
             patch("clipmint.app.threading.Thread",
                   side_effect=run_synchronously):
            w.check_for_updates(manual=True)
            self.app.processEvents()
            self.assertFalse(w._update_busy)
            self.assertTrue(w.check_update_button.isEnabled())
            self.assertIn("Update check failed", w.update_status.text())

    def test_missing_staged_package_cannot_be_opened(self):
        w = self.window
        with patch.object(w, "open_path") as open_package:
            w._on_update_result(
                "0.6.0~preview1.301.1",
                "/missing/clipmint_0.6.0~preview1.301.1_amd64.deb",
                "",
            )
            w.open_verified_update()
            self.assertFalse(w.install_update_button.isEnabled())
            open_package.assert_not_called()


if __name__ == "__main__":
    unittest.main()
