"""Contract tests for the extracted vault presentation controller.

The encryption, keys and persistent vault file format stay in clipmint.vault.
These tests cover delegation and safety-sensitive UI callbacks; the existing
full Qt vault tests verify copy suppression, masking, and passphrase flows.
"""
from __future__ import annotations

from types import SimpleNamespace
import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from clipmint.app import ClipMintWindow
from clipmint.vault_controller import VaultControllerMixin


class VaultControllerExtractionTests(unittest.TestCase):
    def test_window_inherits_existing_vault_actions(self):
        self.assertTrue(issubclass(ClipMintWindow, VaultControllerMixin))
        for name in (
            "refresh_vault", "touch_vault", "vault_password_prompt",
            "create_vault", "unlock_vault", "lock_vault",
            "selected_vault_id", "add_vault_entry", "reveal_vault_value",
            "copy_vault_value", "copy_specific_vault_value",
            "reset_vault_copy_feedback", "expire_vault_clipboard",
            "remove_vault_entry", "change_vault_passphrase",
            "backup_vault", "restore_vault", "wipe_vault",
        ):
            with self.subTest(callback=name):
                self.assertIs(
                    getattr(ClipMintWindow, name),
                    getattr(VaultControllerMixin, name),
                )

    def test_lock_calls_existing_vault_backend_and_refreshes_ui(self):
        lock_timer = Mock()
        vault = SimpleNamespace(lock=Mock())
        state = SimpleNamespace(
            _vault_lock_timer=lock_timer, vault=vault, refresh_vault=Mock()
        )
        VaultControllerMixin.lock_vault(state)
        lock_timer.stop.assert_called_once_with()
        vault.lock.assert_called_once_with()
        state.refresh_vault.assert_called_once_with()

    def test_automated_lock_timer_is_only_extended_while_unlocked(self):
        timer = Mock()
        state = SimpleNamespace(
            vault=SimpleNamespace(unlocked=False), _vault_lock_timer=timer,
        )
        VaultControllerMixin.touch_vault(state)
        timer.start.assert_not_called()
        state.vault.unlocked = True
        VaultControllerMixin.touch_vault(state)
        timer.start.assert_called_once_with(5 * 60 * 1000)

    def test_clipboard_expiry_does_not_clear_another_apps_content(self):
        # A different clipboard owner must not be affected by the old token.
        state = SimpleNamespace(
            _vault_clipboard_token=9,
            _vault_clipboard_text="synthetic-not-a-real-password",
        )
        VaultControllerMixin.expire_vault_clipboard(state, 8)
        self.assertEqual(
            state._vault_clipboard_text, "synthetic-not-a-real-password"
        )

    def test_copy_feedback_reset_has_no_clipboard_side_effects(self):
        button = Mock()
        VaultControllerMixin.reset_vault_copy_feedback(button)
        button.setText.assert_called_once_with("Copy")
        button.setAccessibleName.assert_called_once_with("Copy full value")


if __name__ == "__main__":
    unittest.main()
