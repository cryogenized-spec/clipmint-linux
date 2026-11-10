"""Opt-in temporary retention and verified history archive maintenance.

Window state, encrypted-history migration, clipboard watcher and persistence
remain owned by ClipMintWindow. This module moves only existing callbacks;
no deletion, backup or encryption policy changes are introduced.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3

from PySide6.QtWidgets import QFileDialog, QMessageBox

from .archive_backup import backup_archive, ArchiveBackupError
from .legacy_cleanup import verify_legacy_history, remove_verified_legacy_history
from .secure_history import EncryptedClipStore, HistorySecurityError


class HistoryMaintenanceMixin:
    """Archive backup, verified legacy cleanup and opt-in Temporary expiry."""

    def backup_clipboard_archive(self):
        """Export a verified snapshot; never overwrite without confirmation."""
        if self.history_security_error:
            self.error(
                "Archive backup unavailable",
                "Encrypted history could not be unlocked; no plaintext "
                "fallback backup will be created.",
            )
            return
        destination, _chosen_filter = QFileDialog.getSaveFileName(
            self, "Back up current clipboard archive",
            str(Path.home() / "clipmint-history-backup.sqlite3"),
            "SQLite archive (*.sqlite3)",
        )
        if not destination:
            return
        target = Path(destination).expanduser()
        overwrite = False
        if target.exists() or target.is_symlink():
            answer = QMessageBox.question(
                self, "Replace an existing backup?",
                "A file already exists at that location. Replace it with "
                "a new verified backup of your current ClipMint archive?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            overwrite = True
        if not self.history_secure:
            answer = QMessageBox.question(
                self, "Plaintext archive backup",
                "This history is currently UNENCRYPTED. The backup will also "
                "contain unencrypted clipboard text and images, protected "
                "only by your account's file permissions. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            backup_archive(self.store.conn, target, overwrite=overwrite)
        except (ArchiveBackupError, FileExistsError, OSError) as exc:
            self.error("Archive backup", str(exc))
            return
        self.inform(
            "Archive backup complete",
            "Encrypted archive saved; the desktop keyring key is NOT included."
            if self.history_secure else
            "Archive saved with owner-only permissions (0600). "
            "The contents are NOT encrypted.",
        )

    def remove_old_plaintext_history(self):
        """Only delete legacy data after read-back, user confirmation and recheck."""
        if not self.history_secure or not isinstance(self.store, EncryptedClipStore):
            self.error("Encrypted history", "Unlock encrypted history first")
            return
        try:
            old_path, checked = verify_legacy_history(self.store)
        except (HistorySecurityError, OSError, ValueError) as exc:
            self.error("Legacy history", str(exc))
            return
        answer = QMessageBox.question(
            self, "Remove verified plaintext history?",
            f"Verified {checked} original clipboard entries in the encrypted archive.\n\n"
            "Permanently remove the old plaintext SQLite database and its WAL "
            "sidecars? This cannot be undone. Any separate backups, disk "
            "snapshots or SSD remnant data may still contain plaintext; this "
            "is NOT a forensic secure erase. Make sure your encrypted archive "
            "and keyring key are backed up first.\n\n"
            f"File: {old_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = remove_verified_legacy_history(self.store)
        except (HistorySecurityError, OSError, ValueError) as exc:
            self.error("Legacy history", str(exc))
            return
        self.remove_legacy_button.setEnabled(False)
        self.inform("Legacy history removed",
                    f"Removed old plaintext database after verifying {removed} entries")

    def update_temporary_expiry_schedule(self):
        enabled = (not self.history_security_error and
                   self.settings.value("temporary/expire_24h", False, type=bool))
        if enabled:
            self._temporary_expiry_timer.start()
        else:
            self._temporary_expiry_timer.stop()

    def set_temporary_expiry_enabled(self, enabled: bool):
        if enabled:
            confirmation = QMessageBox.question(
                self, "Enable Temporary expiry?",
                "Automatically delete unpinned Temporary items 24 hours after "
                "they were saved? Any already older than 24 hours will be "
                "removed immediately. Pinned items and other collections "
                "will remain untouched.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirmation != QMessageBox.StandardButton.Yes:
                self.temporary_expiry_toggle.blockSignals(True)
                self.temporary_expiry_toggle.setChecked(False)
                self.temporary_expiry_toggle.blockSignals(False)
                return
        self.settings.setValue("temporary/expire_24h", enabled)
        self.update_temporary_expiry_schedule()
        if enabled:
            self.expire_temporary_if_enabled()

    def invalidate_removed_clip_references(self, removed_ids: list[int]):
        """Never let queued/popup IDs outlive deleted SQLite history rows."""
        if not removed_ids:
            return
        self.paste_queue.discard_ids(removed_ids)
        self._refresh_queue_button()
        if self.quick_popup.isVisible():
            self.quick_popup.refresh()
        else:
            self.quick_popup.items.clear()

    def expire_temporary_if_enabled(self):
        if (self.history_security_error or not self.settings.value(
            "temporary/expire_24h", False, type=bool
        )):
            return
        removed_ids: list[int] = []
        try:
            removed = self.store.expire_temporary_unpinned(
                deleted_ids=removed_ids
            )
        except (sqlite3.DatabaseError, OSError) as exc:
            # Deletions may already be committed even if SQLite maintenance
            # fails. Never let a failure preserve stale queued clipboard IDs.
            self.invalidate_removed_clip_references(removed_ids)
            if removed_ids:
                self.refresh()
            self._temporary_expiry_timer.stop()
            self.error("Temporary expiry", str(exc))
            return
        if removed:
            self.invalidate_removed_clip_references(removed_ids)
            self.refresh()
            self.statusBar().showMessage(
                f"Temporary: {removed} expired unpinned clip(s) removed", 5000
            )

    def clear_temporary_on_normal_exit(self):
        """Never run for crashes, updates, or close-to-tray actions."""
        if self._temporary_exit_cleaned:
            return
        if self.history_security_error or not self.settings.value(
            "temporary/clear_on_quit", False, type=bool
        ):
            return
        try:
            self.store.clear_temporary_unpinned()
        except (sqlite3.DatabaseError, OSError) as exc:
            QMessageBox.warning(
                self, "Temporary cleanup was not completed", str(exc)
            )
            return
        self._temporary_exit_cleaned = True

