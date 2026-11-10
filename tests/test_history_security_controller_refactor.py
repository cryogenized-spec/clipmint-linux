"""Security contracts for the extracted history activation controller."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtWidgets import QMessageBox
from clipmint.app import ClipMintWindow
from clipmint.history_security_controller import HistorySecurityControllerMixin


class SecurityControllerRefactorTests(unittest.TestCase):
    def test_window_delegates_both_encryption_callbacks(self):
        self.assertTrue(issubclass(ClipMintWindow, HistorySecurityControllerMixin))
        for name in ("_initialize_encrypted_history", "enable_encrypted_history"):
            self.assertIs(getattr(ClipMintWindow, name),
                          getattr(HistorySecurityControllerMixin, name))

    def test_startup_without_opt_in_leaves_store_unmodified(self):
        store=SimpleNamespace(close=Mock())
        state=SimpleNamespace(store=store,
            settings=SimpleNamespace(value=lambda *a, **k: False))
        with patch("clipmint.history_security_controller.key_from_secret_service") as key:
            HistorySecurityControllerMixin._initialize_encrypted_history(state)
        self.assertFalse(state.history_secure)
        self.assertEqual(state.history_security_error, "")
        self.assertEqual(state.history_integrity_warning, "")
        self.assertIs(state.store, store)
        store.close.assert_not_called()
        key.assert_not_called()

    def test_missing_secure_file_is_fail_closed_without_creating_key(self):
        store=SimpleNamespace(close=Mock())
        state=SimpleNamespace(store=store,
            settings=SimpleNamespace(value=lambda *a, **k: True))
        with patch("clipmint.history_security_controller.secure_path",
                   return_value=Path("/nonexistent/clipmint/special-test-missing.sqlite3")), \
             patch("clipmint.history_security_controller.key_from_secret_service") as key:
            HistorySecurityControllerMixin._initialize_encrypted_history(state)
        self.assertFalse(state.history_secure)
        self.assertIn("not found", state.history_security_error)
        self.assertIs(state.store, store)
        store.close.assert_not_called()
        key.assert_not_called()

    def test_declining_encryption_does_not_migrate_or_toggle_setting(self):
        state=SimpleNamespace(history_secure=False,
            settings=SimpleNamespace(setValue=Mock()))
        with patch("clipmint.history_security_controller.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.No), \
             patch("clipmint.history_security_controller.key_from_secret_service") as key, \
             patch("clipmint.history_security_controller.EncryptedClipStore") as secure:
            HistorySecurityControllerMixin.enable_encrypted_history(state)
        key.assert_not_called()
        secure.migrate_legacy.assert_not_called()
        state.settings.setValue.assert_not_called()

    def test_keyring_failure_keeps_original_store_and_does_not_resume(self):
        store=SimpleNamespace(close=Mock(),max_total_bytes=None)
        state=SimpleNamespace(history_secure=False,store=store,
            monitoring=False, settings=SimpleNamespace(setValue=Mock()),
            error=Mock())
        from clipmint.secure_history import HistorySecurityError
        with patch("clipmint.history_security_controller.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Yes), \
             patch("clipmint.history_security_controller.key_from_secret_service",
                   side_effect=HistorySecurityError("Keyring locked")), \
             patch("clipmint.history_security_controller.EncryptedClipStore") as secure:
            HistorySecurityControllerMixin.enable_encrypted_history(state)
        self.assertIs(state.store,store)
        self.assertFalse(state.history_secure)
        self.assertFalse(state.monitoring)
        store.close.assert_not_called()
        secure.migrate_legacy.assert_not_called()
        state.settings.setValue.assert_not_called()
        state.error.assert_called_once()

    def test_migration_success_baselines_clipboard_before_monitor_resumes(self):
        events=[]
        store=SimpleNamespace(max_total_bytes=4096,close=Mock())
        secure=SimpleNamespace(max_total_bytes=None)
        probe=SimpleNamespace(observe=Mock(side_effect=lambda _data: events.append("baseline")))
        settings=SimpleNamespace(setValue=Mock(side_effect=lambda *a: events.append("save")))
        state=SimpleNamespace(
            history_secure=False, history_security_error="", monitoring=False,
            store=store, quick_popup=SimpleNamespace(store=store),
            _hidden_text_probe=probe, settings=settings,
            secure_history_button=SimpleNamespace(setText=Mock(),setEnabled=Mock()),
            remove_legacy_button=SimpleNamespace(setEnabled=Mock()),
            refresh=Mock(), inform=Mock()
        )
        with patch("clipmint.history_security_controller.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Yes), \
             patch("clipmint.history_security_controller.key_from_secret_service",
                   return_value=b"dummy-secret"), \
             patch("clipmint.history_security_controller.secure_path",
                   return_value=Path("/tmp/test-only-secret.sqlite3")), \
             patch("clipmint.history_security_controller.EncryptedClipStore") as cls, \
             patch("clipmint.history_security_controller.QApplication") as app:
            cls.migrate_legacy.return_value=secure
            app.clipboard.return_value.mimeData.return_value=object()
            HistorySecurityControllerMixin.enable_encrypted_history(state)
        self.assertIs(state.store,secure)
        self.assertIs(state.quick_popup.store,secure)
        self.assertEqual(secure.max_total_bytes,4096)
        store.close.assert_called_once()
        probe.observe.assert_called_once()
        self.assertTrue(state.history_secure)
        self.assertTrue(state.monitoring)
        settings.setValue.assert_called_once_with("privacy/history_secure",True)
        self.assertEqual(events[:2],["baseline","save"])


if __name__ == "__main__":
    unittest.main()
