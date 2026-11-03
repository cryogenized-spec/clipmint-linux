"""Vault UI safety smoke test with fake credentials and no physical display."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtWidgets import QApplication
from clipmint.app import ClipMintWindow
from clipmint.vault import Vault


class VaultUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_vault_copy_avoids_history_and_conditional_expiry(self):
        with TemporaryDirectory() as root:
            old = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = ClipMintWindow()
                window.vault = Vault(Path(root) / "clipmint" / "private.vault")
                window.vault.create("fake-passphrase-123")
                window.vault.add("fixture", "fake-token-not-real", "Secret")
                window.refresh_vault()
                window.vault_items.setCurrentRow(0)
                self.assertTrue(window.vault_actions["copy"].isEnabled())
                window.copy_vault_value()
                self.assertEqual(QApplication.clipboard().text(),
                                 "fake-token-not-real")
                window.clipboard_changed()
                self.assertEqual(window.store.count("Work"), 0)
                # Never wipe later clipboard content written by another app.
                QApplication.clipboard().setText("other-app-contents")
                window.expire_vault_clipboard(window._vault_clipboard_token)
                self.assertEqual(QApplication.clipboard().text(),
                                 "other-app-contents")
                window.lock_vault()
                self.assertFalse(window.vault.unlocked)
                self.assertEqual(window.vault_items.count(), 0)
            finally:
                if window is not None:
                    window.poller.stop()
                    window._vault_lock_timer.stop()
                    window.vault.lock()
                    window.store.close()
                    window.hide()
                if old is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = old


if __name__ == "__main__":
    unittest.main()
