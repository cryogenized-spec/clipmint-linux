"""Safety contracts for extracted history/Temporary maintenance callbacks.

Deletion and migration workflows are exercised with stubs only.
"""
from __future__ import annotations

import os
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtWidgets import QMessageBox

from clipmint.app import ClipMintWindow
from clipmint.history_maintenance_controller import HistoryMaintenanceMixin


class HistoryMaintenanceRefactorTests(unittest.TestCase):
    def test_main_window_preserves_maintenance_callbacks(self):
        self.assertTrue(issubclass(ClipMintWindow, HistoryMaintenanceMixin))
        for method in (
            "backup_clipboard_archive", "remove_old_plaintext_history",
            "update_temporary_expiry_schedule",
            "set_temporary_expiry_enabled", "invalidate_removed_clip_references",
            "expire_temporary_if_enabled", "clear_temporary_on_normal_exit",
        ):
            with self.subTest(method=method):
                self.assertIs(getattr(ClipMintWindow, method),
                              getattr(HistoryMaintenanceMixin, method))

    def test_failed_encrypted_history_unlock_prevents_backup_dialog(self):
        state = SimpleNamespace(
            history_security_error="Cannot unlock desktop keyring",
            error=Mock(),
        )
        with patch("clipmint.history_maintenance_controller.QFileDialog") as dialog:
            HistoryMaintenanceMixin.backup_clipboard_archive(state)
            dialog.getSaveFileName.assert_not_called()
        state.error.assert_called_once()

    def test_legacy_cleanup_requires_verified_encrypted_store(self):
        state = SimpleNamespace(
            history_secure=False, store=SimpleNamespace(), error=Mock(),
        )
        with patch("clipmint.history_maintenance_controller.verify_legacy_history") as verify:
            HistoryMaintenanceMixin.remove_old_plaintext_history(state)
        verify.assert_not_called()
        state.error.assert_called_once()

    def test_declined_temporary_expiry_never_enables_or_prunes(self):
        toggle = SimpleNamespace(blockSignals=Mock(), setChecked=Mock())
        state = SimpleNamespace(
            temporary_expiry_toggle=toggle,
            settings=SimpleNamespace(setValue=Mock()),
            update_temporary_expiry_schedule=Mock(),
            expire_temporary_if_enabled=Mock(),
        )
        with patch("clipmint.history_maintenance_controller.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.No):
            HistoryMaintenanceMixin.set_temporary_expiry_enabled(state, True)
        toggle.setChecked.assert_called_once_with(False)
        state.settings.setValue.assert_not_called()
        state.update_temporary_expiry_schedule.assert_not_called()
        state.expire_temporary_if_enabled.assert_not_called()

    def test_no_temporary_cleanup_without_explicit_opt_in(self):
        store=SimpleNamespace(clear_temporary_unpinned=Mock())
        state=SimpleNamespace(
            _temporary_exit_cleaned=False, history_security_error="",
            settings=SimpleNamespace(value=lambda *args, **kwargs: False),
            store=store,
        )
        HistoryMaintenanceMixin.clear_temporary_on_normal_exit(state)
        store.clear_temporary_unpinned.assert_not_called()
        self.assertFalse(state._temporary_exit_cleaned)

    def test_locked_history_cannot_enable_expiry_timer(self):
        timer=SimpleNamespace(start=Mock(), stop=Mock())
        state=SimpleNamespace(
            history_security_error="Key unavailable",
            settings=SimpleNamespace(value=lambda *args, **kwargs: True),
            _temporary_expiry_timer=timer,
        )
        HistoryMaintenanceMixin.update_temporary_expiry_schedule(state)
        timer.start.assert_not_called()
        timer.stop.assert_called_once_with()

    def test_failed_expiry_invalidates_deleted_queue_ids(self):
        def partial_failure(*, deleted_ids):
            deleted_ids.append(42)
            raise sqlite3.DatabaseError("SQL maintenance failed")
        state=SimpleNamespace(
            history_security_error="",
            settings=SimpleNamespace(value=lambda *args, **kwargs: True),
            store=SimpleNamespace(expire_temporary_unpinned=partial_failure),
            invalidate_removed_clip_references=Mock(),
            refresh=Mock(),
            _temporary_expiry_timer=SimpleNamespace(stop=Mock()),
            error=Mock(),
        )
        HistoryMaintenanceMixin.expire_temporary_if_enabled(state)
        state.invalidate_removed_clip_references.assert_called_once_with([42])
        state.refresh.assert_called_once_with()
        state._temporary_expiry_timer.stop.assert_called_once_with()
        state.error.assert_called_once()

    def test_exit_cleanup_is_idempotent(self):
        store=SimpleNamespace(clear_temporary_unpinned=Mock())
        state=SimpleNamespace(
            _temporary_exit_cleaned=False, history_security_error="",
            settings=SimpleNamespace(value=lambda *args, **kwargs: True),
            store=store,
        )
        HistoryMaintenanceMixin.clear_temporary_on_normal_exit(state)
        HistoryMaintenanceMixin.clear_temporary_on_normal_exit(state)
        store.clear_temporary_unpinned.assert_called_once_with()
        self.assertTrue(state._temporary_exit_cleaned)


if __name__ == "__main__":
    unittest.main()
