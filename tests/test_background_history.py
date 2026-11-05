"""Closing the ClipMint interface must not stop clipboard history capture."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtWidgets import QApplication
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
