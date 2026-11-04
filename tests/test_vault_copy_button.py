"""One-click vault copy regression tests; credentials are synthetic fixtures only."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QPushButton
from clipmint.app import ClipMintWindow


FAKE_VALUE = "SYNTHETIC_ONLY_not-a-real-client-secret_0123456789"


class VaultCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_reveal_dialog_copies_full_masked_value_in_one_click(self):
        with TemporaryDirectory() as root:
            old = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = ClipMintWindow()
                window.vault.create("fake-vault-passphrase-123")
                entry_id = window.vault.add("Synthetic test entry", FAKE_VALUE, "Secret")
                window.refresh_vault()
                self.assertEqual(window.vault_items.count(), 1)
                window.vault_items.setCurrentRow(0)
                self.assertEqual(window.selected_vault_id(), entry_id)

                observed = []
                def inspect_dialog(dialog):
                    copy = dialog.findChild(QPushButton, "vaultRevealCopy")
                    self.assertIsNotNone(copy)
                    field = next(
                        value for value in dialog.findChildren(QLineEdit)
                        if value.text() == FAKE_VALUE
                    )
                    self.assertTrue(field.isReadOnly())
                    self.assertEqual(field.echoMode(), QLineEdit.EchoMode.Password)
                    self.assertEqual(copy.text(), "Copy")
                    self.assertNotIn(FAKE_VALUE, copy.text())
                    # No selection and no reveal: still copies the entire value.
                    self.assertEqual(field.selectedText(), "")
                    copy.click()
                    self.app.processEvents()
                    self.assertEqual(QApplication.clipboard().text(), FAKE_VALUE)
                    self.assertEqual(copy.text(), "✓ Copied!")
                    self.assertEqual(window.statusBar().currentMessage(), "Copied!")
                    self.assertEqual(window.store.count("Work"), 0)
                    self.assertEqual(window._vault_clipboard_text, FAKE_VALUE)
                    self.assertTrue(copy._clipmint_copy_timer.isActive())

                    # Dots stay on screen even after copying.
                    self.assertEqual(field.echoMode(), QLineEdit.EchoMode.Password)
                    self.assertNotIn(FAKE_VALUE, dialog.windowTitle())
                    for label in dialog.findChildren(QLabel):
                        self.assertNotIn(FAKE_VALUE, label.text())

                    # Timer visual feedback can safely reset without changing clipboard.
                    copy._clipmint_copy_timer.stop()
                    window.reset_vault_copy_feedback(copy)
                    self.assertEqual(copy.text(), "Copy")
                    self.assertEqual(QApplication.clipboard().text(), FAKE_VALUE)
                    observed.append(True)
                    return QDialog.DialogCode.Rejected

                with patch.object(QDialog, "exec", inspect_dialog):
                    window.reveal_vault_value()
                self.assertEqual(observed, [True])
                self.assertEqual(window.store.count("Work"), 0)
                window.expire_vault_clipboard(window._vault_clipboard_token)
                self.assertEqual(QApplication.clipboard().text(), "")
            finally:
                if window is not None:
                    window.poller.stop()
                    window._vault_lock_timer.stop()
                    window.store.close()
                    window.close()
                if old is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = old

    def test_main_vault_copy_also_uses_feedback_and_never_saves_history(self):
        with TemporaryDirectory() as root:
            old = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = ClipMintWindow()
                window.vault.create("fake-vault-passphrase-123")
                window.vault.add("Fake token", FAKE_VALUE, "Secret")
                window.refresh_vault()
                window.vault_items.setCurrentRow(0)
                copy_button = window.vault_actions["copy"]
                copy_button.click()
                self.app.processEvents()
                self.assertEqual(QApplication.clipboard().text(), FAKE_VALUE)
                self.assertEqual(copy_button.text(), "✓ Copied!")
                self.assertEqual(window.statusBar().currentMessage(), "Copied!")
                self.assertEqual(window.store.count("Work"), 0)
                copy_button._clipmint_copy_timer.stop()
                window.expire_vault_clipboard(window._vault_clipboard_token)
                self.assertEqual(QApplication.clipboard().text(), "")
            finally:
                if window is not None:
                    window.poller.stop()
                    window._vault_lock_timer.stop()
                    window.store.close()
                    window.close()
                if old is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = old


if __name__ == "__main__":
    unittest.main()
