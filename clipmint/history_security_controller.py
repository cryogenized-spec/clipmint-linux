"""Encrypted clipboard history activation and locked-keyring recovery.

Keep existing security semantics: encrypted history is opt-in; missing keys
and missing secure files fail closed, migration never automatically deletes
the legacy plaintext database, and monitoring baselines the live clipboard
before resuming. Cryptography and SQLite remain in secure_history.py.
"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication, QMessageBox

from .secure_history import (
    EncryptedClipStore, HistorySecurityError, key_from_secret_service,
    secure_path,
)


class HistorySecurityControllerMixin:
    """Startup unlock and explicit encrypted-history migration callbacks."""

    def _initialize_encrypted_history(self) -> None:
        """Only unlock encrypted history when the stored opt-in says so."""
        self.history_secure = False
        self.history_security_error = ""
        self.history_integrity_warning = ""
        if self.settings.value("privacy/history_secure", False, type=bool):
            try:
                if not secure_path().is_file():
                    raise HistorySecurityError("Encrypted history file not found")
                key = key_from_secret_service(create=False)
                encrypted = EncryptedClipStore(secure_path(), key)
                self.store.close()
                self.store = encrypted
                self.history_secure = True
                if encrypted.corrupt_row_ids:
                    self.history_integrity_warning = (
                        f"Warning: {len(encrypted.corrupt_row_ids)} unreadable "
                        "encrypted history item(s) hidden, not deleted."
                    )
            except (HistorySecurityError, OSError) as exc:
                self.history_security_error = str(exc)

    def enable_encrypted_history(self):
        if self.history_secure:
            return
        confirmation = QMessageBox.question(
            self, "Encrypt clipboard history",
            "This creates a separate encrypted SQLite database using your unlocked "
            "desktop Secret Service keyring. The original plaintext database is "
            "preserved for recovery. After verification, you may optionally remove "
            "the old plaintext database in Settings. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        try:
            key = key_from_secret_service(create=True)
            secure = EncryptedClipStore.migrate_legacy(
                self.store, secure_path(), key
            )
        except (HistorySecurityError, OSError, ValueError) as exc:
            self.error("Encrypted history", str(exc))
            return
        secure.max_total_bytes = self.store.max_total_bytes
        self.store.close()
        self.store = secure
        self.quick_popup.store = secure
        self.history_secure = True
        self.history_security_error = ""
        # Enabling encrypted history also resumes monitoring. Just like
        # Resume, baseline the current clipboard first so paused text cannot
        # leak into the new encrypted archive on the next hidden poll.
        self._hidden_text_probe.observe(QApplication.clipboard().mimeData())
        self.monitoring = True
        self.settings.setValue("privacy/history_secure", True)
        self.secure_history_button.setText("Encrypted history active")
        self.secure_history_button.setEnabled(False)
        self.remove_legacy_button.setEnabled(True)
        self.refresh()
        self.inform(
            "History encrypted",
            "New captures are encrypted. The old plaintext history still exists."
        )

