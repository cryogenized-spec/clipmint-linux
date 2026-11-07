"""Closing the ClipMint interface must not stop clipboard history capture."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest

from clipmint.app import ClipMintWindow
from clipmint.store import ClipStore


class BackgroundHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hidden_without_tray_still_records_external_clipboard_text(self):
        with TemporaryDirectory() as root:
            old_data = os.environ.get("XDG_DATA_HOME")
            old_config = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_DATA_HOME"] = root
            os.environ["XDG_CONFIG_HOME"] = str(Path(root) / "settings")
            window = None
            try:
                # Explicitly exercise the no-tray path. Monitoring must not
                # depend on Qt's panel/tray icon availability.
                self.app.setQuitOnLastWindowClosed(False)
                with patch("clipmint.app.blocked_foreground", return_value=False):
                    window = ClipMintWindow()
                    if window.tray is not None:
                        window.tray.hide()
                        window.tray = None
                    window.autosort_enabled = False
                    window.show()
                    self.app.processEvents()
                    self.assertTrue(window.isVisible())
                    window.close()
                    self.app.processEvents()
                    self.assertFalse(window.isVisible())
                    self.assertFalse(window.store.closed)
                    self.assertTrue(window.monitoring)
                    self.assertIn("MONITORING ACTIVE", window.footer_status.text())

                    sample = "Background clipboard capture after closing window"
                    QApplication.clipboard().setText(sample)
                    QTest.qWait(250)
                    records = window.store.search(sample, "Work")
                    self.assertTrue(records, "Hidden watcher did not save copied text")
                    self.assertEqual(window.store.get(records[0].id), (
                        "text", sample.encode("utf-8")
                    ))

                    window.show_window()
                    self.app.processEvents()
                    self.assertTrue(window.isVisible())
                    self.assertTrue(window.store.search(sample, "Work"))
                    path = window.store.path
                    window._closing = True
                    window.store.close()
                    window.close()
                    window.deleteLater()
                    window = None
                    # The event was committed, not just held by an in-memory UI.
                    reopened = ClipStore(path)
                    try:
                        self.assertTrue(reopened.search(sample, "Work"))
                    finally:
                        reopened.close()
            finally:
                if window is not None:
                    window._closing = True
                    if not window.store.closed:
                        window.store.close()
                    window.close()
                    window.deleteLater()
                if old_data is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = old_data
                if old_config is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = old_config

    def test_startup_does_not_retroactively_save_preexisting_clipboard(self):
        """An explicit Quit ends monitoring; reopening starts a NEW session."""
        with TemporaryDirectory() as root:
            old_data = os.environ.get("XDG_DATA_HOME")
            old_config = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_DATA_HOME"] = root
            os.environ["XDG_CONFIG_HOME"] = str(Path(root) / "settings")
            window = None
            try:
                self.app.setQuitOnLastWindowClosed(False)
                old_copy = "Copied while no ClipMint watcher was running 20261107"
                self.app.clipboard().setText(old_copy)
                window = ClipMintWindow()
                if window.tray is not None:
                    window.tray.hide()
                    window.tray = None
                window.autosort_enabled = False
                window.show()
                self.app.processEvents()
                window.close()
                self.app.processEvents()
                QTest.qWait(1800)
                self.assertEqual(window.store.search(old_copy, None), [])

                new_copy = "New copy after ClipMint background watcher starts"
                with patch("clipmint.app.blocked_foreground", return_value=False):
                    self.app.clipboard().setText(new_copy)
                    QTest.qWait(250)
                self.assertEqual(len(window.store.search(new_copy, None)), 1)
            finally:
                if window is not None:
                    window._hidden_clipboard_timer.stop()
                    window._closing = True
                    if not window.store.closed:
                        window.store.close()
                    window.close()
                    window.deleteLater()
                if old_data is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = old_data
                if old_config is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = old_config

    def test_hidden_probe_recovers_text_without_data_changed_signal(self):
        """Missed X11 signals must not lose copied text while UI is closed."""
        with TemporaryDirectory() as root:
            old_data = os.environ.get("XDG_DATA_HOME")
            old_config = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_DATA_HOME"] = root
            os.environ["XDG_CONFIG_HOME"] = str(Path(root) / "settings")
            window = None
            disconnected = False
            try:
                self.app.setQuitOnLastWindowClosed(False)
                with patch("clipmint.app.blocked_foreground", return_value=False):
                    window = ClipMintWindow()
                    if window.tray is not None:
                        window.tray.hide()
                        window.tray = None
                    window.autosort_enabled = False
                    window.show()
                    self.app.processEvents()
                    window.close()
                    self.app.processEvents()
                    self.assertFalse(window.isVisible())
                    self.assertTrue(window._hidden_clipboard_timer.isActive())

                    # Reproduce a missed Qt X11 notification: the window
                    # remains alive, but the normal capture callback is
                    # disconnected. Only the hidden probe can save this copy.
                    self.app.clipboard().dataChanged.disconnect(
                        window.clipboard_changed
                    )
                    disconnected = True
                    sample = "Hidden clipboard recovery 20261107 unique sample"
                    self.app.clipboard().setText(sample)
                    self.app.processEvents()
                    self.assertFalse(window.store.search(sample, None))
                    window.poll_hidden_clipboard()
                    saved = window.store.search(sample, None)
                    self.assertEqual(len(saved), 1)
                    self.assertEqual(window.store.get(saved[0].id),
                                     ("text", sample.encode("utf-8")))

                    # Repeated polls must never artificially 'recopy' a clip.
                    before = window.store.conn.execute(
                        "SELECT touch_seq FROM clips WHERE id=?", (saved[0].id,)
                    ).fetchone()[0]
                    window.poll_hidden_clipboard()
                    after = window.store.conn.execute(
                        "SELECT touch_seq FROM clips WHERE id=?", (saved[0].id,)
                    ).fetchone()[0]
                    self.assertEqual(before, after)

                    # Even if resume happens BEFORE the next 1500-ms timer,
                    # paused content must not leak into history. This was
                    # caught during independent code review.
                    window.toggle_monitoring()
                    self.assertFalse(window.monitoring)
                    self.assertIn("MONITORING PAUSED", window.footer_status.text())
                    skipped = "Do not save this while paused 20261107"
                    self.app.clipboard().setText(skipped)
                    window.toggle_monitoring()
                    self.assertTrue(window.monitoring)
                    window.poll_hidden_clipboard()
                    self.assertEqual(window.store.search(skipped, None), [])

                    next_text = "New clipboard content after resuming 20261107"
                    self.app.clipboard().setText(next_text)
                    window.poll_hidden_clipboard()
                    self.assertEqual(len(window.store.search(next_text, None)), 1)
            finally:
                if window is not None:
                    window._hidden_clipboard_timer.stop()
                    if disconnected:
                        self.app.clipboard().dataChanged.connect(
                            window.clipboard_changed
                        )
                    window._closing = True
                    if not window.store.closed:
                        window.store.close()
                    window.hide()
                    window.deleteLater()
                if old_data is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = old_data
                if old_config is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = old_config

    def test_encryption_toggle_cannot_capture_previously_paused_text(self):
        """Enabling encrypted history is another resume path; baseline it."""
        from nacl import utils
        from nacl.secret import SecretBox
        with TemporaryDirectory() as root:
            old_data = os.environ.get("XDG_DATA_HOME")
            old_config = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_DATA_HOME"] = root
            os.environ["XDG_CONFIG_HOME"] = str(Path(root) / "settings")
            window = None
            disconnected = False
            try:
                self.app.setQuitOnLastWindowClosed(False)
                # Encryption writes a persistent privacy/history_secure
                # flag. Keep this test's Qt preferences PRIVATE; otherwise
                # later unrelated tests instantiate an encrypted/locked
                # history without a keyring and stop monitoring.
                prefs = str(Path(root) / "private-encryption-test.ini")
                with patch("clipmint.app.QSettings",
                           side_effect=lambda *_: QSettings(
                               prefs, QSettings.Format.IniFormat)):
                    window = ClipMintWindow()
                if window.tray is not None:
                    window.tray.hide()
                    window.tray = None
                window.autosort_enabled = False
                window.show()
                self.app.processEvents()
                window.close()
                self.app.processEvents()
                window.monitoring = False
                self.app.clipboard().dataChanged.disconnect(window.clipboard_changed)
                disconnected = True

                skipped = "Never import text copied during encryption pause 20261107"
                self.app.clipboard().setText(skipped)
                secret_file = Path(root) / "encrypted-history.sqlite3"
                key = utils.random(SecretBox.KEY_SIZE)
                with patch.object(
                    QMessageBox, "question",
                    return_value=QMessageBox.StandardButton.Yes
                ), patch(
                    "clipmint.app.key_from_secret_service", return_value=key
                ), patch(
                    "clipmint.app.secure_path", return_value=secret_file
                ), patch(
                    "clipmint.app.blocked_foreground", return_value=False
                ):
                    window.enable_encrypted_history()
                    self.assertTrue(window.monitoring)
                    self.assertTrue(window.history_secure)
                    window.poll_hidden_clipboard()
                    self.assertFalse(window.store.search(skipped, None))
                    copied = "Fresh protected clip after enabling encryption"
                    self.app.clipboard().setText(copied)
                    window.poll_hidden_clipboard()
                    self.assertEqual(len(window.store.search(copied, None)), 1)
            finally:
                if window is not None:
                    window._hidden_clipboard_timer.stop()
                    if disconnected:
                        self.app.clipboard().dataChanged.connect(window.clipboard_changed)
                    window._closing = True
                    if not window.store.closed:
                        window.store.close()
                    window.close()
                    window.deleteLater()
                if old_data is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = old_data
                if old_config is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = old_config

    def test_background_app_lifetime_configuration_is_explicit(self):
        # The launcher must override Qt's default "exit when last window closes".
        app_source = (Path(__file__).resolve().parents[1] / "clipmint/app.py"
                     ).read_text(encoding="utf-8")
        self.assertIn("app.setQuitOnLastWindowClosed(False)", app_source)
        self.assertIn("elif hidden:", app_source)
        self.assertIn("self.hide()\n        event.ignore()", app_source)
        self.assertIn("quit_background_button.clicked.connect(self.quit_app)",
                      app_source)


if __name__ == "__main__":
    unittest.main()
