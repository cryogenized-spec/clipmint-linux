"""Sensitive clipboard countdown tests (only synthetic OTP and secret strings)."""
from __future__ import annotations

import os
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtWidgets import QApplication
from clipmint.app import ClipMintWindow


class SensitiveClipboardExpiryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_otp_is_excluded_and_only_unchanged_content_is_cleared(self):
        with TemporaryDirectory() as root:
            old_data = os.environ.get("XDG_DATA_HOME")
            old_config = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_DATA_HOME"] = root
            os.environ["XDG_CONFIG_HOME"] = root
            window = None
            try:
                window = ClipMintWindow()
                clipboard = QApplication.clipboard()

                clipboard.setText("583129")
                self.app.processEvents()
                first_token = window._sensitive_clipboard_token
                self.assertGreater(first_token, 0)
                self.assertEqual(window.store.count("Work"), 0)

                clipboard.setText("Benign new item")
                self.app.processEvents()
                window.expire_sensitive_clipboard(first_token, "583129")
                self.assertEqual(clipboard.text(), "Benign new item")

                clipboard.setText("583129")
                self.app.processEvents()
                latest = window._sensitive_clipboard_token
                self.assertGreater(latest, first_token)
                window.expire_sensitive_clipboard(first_token, "583129")
                self.assertEqual(clipboard.text(), "583129")
                window.expire_sensitive_clipboard(latest, "583129")
                self.assertEqual(clipboard.text(), "")
            finally:
                if window is not None:
                    window.poller.stop()
                    window._vault_lock_timer.stop()
                    window.store.close()
                    window.hide()
                QApplication.clipboard().clear()
                if old_data is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = old_data
                if old_config is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = old_config


if __name__ == "__main__":
    unittest.main()
