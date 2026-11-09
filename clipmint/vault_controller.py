"""Vault presentation and user-action controller for ClipMint's main window.

The storage/cryptography remains in vault.py. These Qt callbacks preserve the
existing passphrase prompts, opt-in use, clipboard suppression, temporary
expiry and confirmation flows without changing any vault data or key format.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QInputDialog, QLabel, QLineEdit,
    QListWidgetItem, QMessageBox, QPushButton,
)

from .vault import VaultError


class VaultControllerMixin:
    def refresh_vault(self):
        configured, unlocked = self.vault.configured, self.vault.unlocked
        self.vault_status.setText(
            "● UNLOCKED · decrypted in memory temporarily" if unlocked
            else "● LOCKED · passphrase required" if configured
            else "● NOT CONFIGURED · create a private vault"
        )
        self.vault_items.clear()
        if unlocked:
            for entry in self.vault.list_entries():
                item = QListWidgetItem(
                    f"{entry['kind'].upper()}  ·  {entry['name']}"
                )
                item.setData(Qt.ItemDataRole.UserRole, entry["id"])
                self.vault_items.addItem(item)
        for name, button in self.vault_actions.items():
            button.setEnabled({
                "create": not configured,
                "restore": not configured,
                "unlock": configured and not unlocked,
                "lock": unlocked,
                "backup": configured,
                "wipe": configured,
                "add": unlocked, "reveal": unlocked,
                "copy": unlocked, "remove": unlocked,
                "rotate": unlocked,
            }[name])

    def touch_vault(self):
        if self.vault.unlocked:
            self._vault_lock_timer.start(5 * 60 * 1000)

    def vault_password_prompt(self, title: str, message: str) -> str | None:
        value, ok = QInputDialog.getText(
            self, title, message, QLineEdit.EchoMode.Password
        )
        return value if ok else None

    def create_vault(self):
        password = self.vault_password_prompt(
            "Create encrypted vault", "Choose a passphrase (at least 12 characters):"
        )
        if password is None:
            return
        again = self.vault_password_prompt(
            "Confirm passphrase", "Enter the same passphrase again:"
        )
        if again is None:
            return
        if password != again:
            self.error("Vault", "Passphrases do not match")
            return
        try:
            self.vault.create(password)
            self.refresh_vault()
            self.touch_vault()
            self.inform(
                "Vault created",
                "Keep your passphrase safe. There is no recovery without it."
            )
        except VaultError as exc:
            self.error("Vault", str(exc))

    def unlock_vault(self):
        password = self.vault_password_prompt("Unlock vault", "Vault passphrase:")
        if password is None:
            return
        try:
            self.vault.unlock(password)
            self.refresh_vault()
            self.touch_vault()
        except VaultError as exc:
            self.error("Vault", str(exc))

    def lock_vault(self):
        self._vault_lock_timer.stop()
        self.vault.lock()
        self.refresh_vault()

    def selected_vault_id(self) -> str | None:
        item = self.vault_items.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def add_vault_entry(self):
        if not self.vault.unlocked:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Save encrypted entry")
        fields = QFormLayout(dialog)
        kind = QComboBox()
        kind.addItems(["Secret", "Variable"])
        name = QLineEdit()
        value = QLineEdit()
        value.setEchoMode(QLineEdit.EchoMode.Password)
        value.setPlaceholderText("Stored encrypted; never captured as history")
        kind.currentTextChanged.connect(
            lambda text: value.setEchoMode(
                QLineEdit.EchoMode.Password if text == "Secret"
                else QLineEdit.EchoMode.Normal
            )
        )
        fields.addRow("Type", kind)
        fields.addRow("Name", name)
        fields.addRow("Value", value)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        fields.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.vault.add(name.text(), value.text(), kind.currentText())
            value.clear()
            self.touch_vault()
            self.refresh_vault()
        except VaultError as exc:
            self.error("Vault", str(exc))

    def reveal_vault_value(self):
        entry_id = self.selected_vault_id()
        if entry_id is None or not self.vault.unlocked:
            return
        try:
            value = self.vault.get_value(entry_id)
        except VaultError as exc:
            self.error("Vault", str(exc))
            return
        self.touch_vault()
        dialog = QDialog(self)
        dialog.setWindowTitle("Reveal saved entry")
        form = QFormLayout(dialog)
        field = QLineEdit(value)
        field.setReadOnly(True)
        field.setEchoMode(QLineEdit.EchoMode.Password)
        reveal = QCheckBox("Show value while this dialog is open")
        reveal.toggled.connect(
            lambda checked: field.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        # Copy the full value directly from the unlocked vault, regardless
        # of cursor position, text selection or masked display state.
        copy_button = QPushButton("Copy")
        copy_button.setObjectName("vaultRevealCopy")
        copy_button.setToolTip("Copy the complete value without revealing it")
        copy_button.clicked.connect(
            lambda _checked=False: self.copy_specific_vault_value(
                entry_id, feedback_button=copy_button
            )
        )
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        form.addRow("Value", field)
        form.addRow("", reveal)
        form.addRow("Clipboard", copy_button)
        clipboard_note = QLabel("Clipboard clears after 30 seconds if unchanged.")
        clipboard_note.setObjectName("captureDetails")
        form.addRow("", clipboard_note)
        form.addRow(close)
        dialog.exec()
        field.clear()

    def copy_vault_value(self, *_args):
        """Copy from the main vault list without relying on selected text."""
        entry_id = self.selected_vault_id()
        if entry_id is not None:
            self.copy_specific_vault_value(
                entry_id, feedback_button=self.vault_actions.get("copy")
            )

    def copy_specific_vault_value(
        self, entry_id: str, *, feedback_button: QPushButton | None = None
    ) -> None:
        """Copy the entire decrypted value; never add it to clipboard history."""
        if not self.vault.unlocked:
            return
        try:
            value = self.vault.get_value(entry_id)
        except VaultError as exc:
            self.error("Vault", str(exc))
            return
        self.touch_vault()
        self._vault_clipboard_text = value
        self._vault_clipboard_token += 1
        token = self._vault_clipboard_token
        self._own_clipboard_guard.note_text(value)
        QApplication.clipboard().setText(value)
        QTimer.singleShot(30000, lambda: self.expire_vault_clipboard(token))

        if feedback_button is not None:
            feedback_button.setText("✓ Copied!")
            feedback_button.setAccessibleName("Copied!")
            # A timer owned by the button can't update a closed dialog.
            timer = getattr(feedback_button, "_clipmint_copy_timer", None)
            if timer is None:
                timer = QTimer(feedback_button)
                timer.setSingleShot(True)
                timer.timeout.connect(
                    lambda: self.reset_vault_copy_feedback(feedback_button)
                )
                feedback_button._clipmint_copy_timer = timer
            timer.start(1800)
        self.statusBar().showMessage("Copied!", 3000)

    @staticmethod
    def reset_vault_copy_feedback(button: QPushButton) -> None:
        button.setText("Copy")
        button.setAccessibleName("Copy full value")

    def expire_vault_clipboard(self, token: int):
        if token != self._vault_clipboard_token:
            return
        value = self._vault_clipboard_text
        if value is not None and QApplication.clipboard().text() == value:
            QApplication.clipboard().clear()
        self._vault_clipboard_text = None

    def remove_vault_entry(self):
        entry_id = self.selected_vault_id()
        if entry_id is None:
            return
        if QMessageBox.question(
            self, "Delete entry",
            "Permanently delete this vault entry?",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.vault.remove(entry_id)
            self.touch_vault()
            self.refresh_vault()
        except VaultError as exc:
            self.error("Vault", str(exc))

    def change_vault_passphrase(self):
        if not self.vault.unlocked:
            return
        old = self.vault_password_prompt("Change passphrase", "Current passphrase:")
        if old is None:
            return
        new = self.vault_password_prompt("Change passphrase", "New passphrase:")
        if new is None:
            return
        confirm = self.vault_password_prompt("Confirm passphrase", "Repeat new passphrase:")
        if confirm is None:
            return
        if new != confirm:
            self.error("Vault", "Passphrases do not match")
            return
        try:
            self.vault.change_passphrase(old, new)
            self.touch_vault()
            self.inform("Vault", "Passphrase updated. Create a fresh encrypted backup.")
        except VaultError as exc:
            self.error("Vault", str(exc))

    def backup_vault(self):
        if not self.vault.configured:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save encrypted vault backup", "clipmint-vault-backup.json",
            "Encrypted vault (*.json *.vault)"
        )
        if not filename:
            return
        try:
            self.vault.encrypted_backup(Path(filename))
            self.inform("Vault backup", "Encrypted backup saved. Retain its passphrase.")
        except VaultError as exc:
            self.error("Vault", str(exc))

    def restore_vault(self):
        if self.vault.configured:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Restore encrypted vault backup", "",
            "Encrypted vault (*.json *.vault)"
        )
        if not filename:
            return
        try:
            self.vault.restore_backup(Path(filename))
            self.refresh_vault()
            self.inform("Vault", "Encrypted backup restored. Unlock with its original passphrase.")
        except VaultError as exc:
            self.error("Vault", str(exc))

    def wipe_vault(self):
        if not self.vault.configured:
            return
        response, ok = QInputDialog.getText(
            self, "Delete encrypted vault",
            "This deletes the local encrypted file. Backups are not deleted. "
            "Type DELETE to confirm:",
        )
        if not ok or response != "DELETE":
            return
        try:
            self._vault_lock_timer.stop()
            self.vault.wipe()
            self.refresh_vault()
            self.inform("Vault deleted", "Local encrypted vault removed.")
        except VaultError as exc:
            self.error("Vault", str(exc))

