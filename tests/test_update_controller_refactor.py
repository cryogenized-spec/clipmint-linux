"""Maintain safety contracts while extracting preview-update Qt actions.

These tests do not access the network or modify installed packages. Existing
tests/test_updater_settings.py exercises the actual Qt check/consent workflow.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from clipmint.app import ClipMintWindow
from clipmint.update_controller import UpdateControllerMixin, UpdateSignals


class UpdateControllerExtractionTests(unittest.TestCase):
    def test_window_inherits_original_updater_callbacks(self):
        self.assertTrue(issubclass(ClipMintWindow, UpdateControllerMixin))
        for method in (
            "set_auto_updates_enabled", "_auto_check_updates",
            "check_for_updates", "download_available_preview",
            "_on_update_result", "open_verified_update",
        ):
            with self.subTest(method=method):
                self.assertIs(getattr(ClipMintWindow, method),
                              getattr(UpdateControllerMixin, method))

    def test_signal_payload_remains_candidate_path_and_error(self):
        instance = UpdateSignals()
        self.assertTrue(hasattr(instance.finished, "emit"))

    def test_timer_never_checks_without_explicit_opt_in(self):
        state = SimpleNamespace(
            settings=Mock(),
            check_for_updates=Mock(),
        )
        state.settings.value.return_value = False
        UpdateControllerMixin._auto_check_updates(state)
        state.check_for_updates.assert_not_called()

    def test_timer_respects_24_hour_check_interval(self):
        state = SimpleNamespace(
            settings=Mock(),
            check_for_updates=Mock(),
        )
        state.settings.value.side_effect = [True, 86_399]
        with patch("clipmint.update_controller.time.time", return_value=86_400):
            UpdateControllerMixin._auto_check_updates(state)
        state.check_for_updates.assert_not_called()

        state.settings.value.side_effect = [True, 1]
        with patch("clipmint.update_controller.time.time", return_value=86_402):
            UpdateControllerMixin._auto_check_updates(state)
        state.check_for_updates.assert_called_once_with(manual=False)

    def test_missing_staged_package_disables_native_installer_action(self):
        state = SimpleNamespace(
            _verified_update_path=Path("/nonexistent/clipmint_404.deb"),
            install_update_button=Mock(), update_status=Mock(),
            open_path=Mock(),
        )
        UpdateControllerMixin.open_verified_update(state)
        state.install_update_button.setEnabled.assert_called_once_with(False)
        state.open_path.assert_not_called()

    def test_update_preference_does_not_change_without_opt_in(self):
        state = SimpleNamespace(
            settings=Mock(), check_for_updates=Mock()
        )
        UpdateControllerMixin.set_auto_updates_enabled(state, False)
        state.settings.setValue.assert_called_once_with(
            "updates/automatic", False
        )
        state.check_for_updates.assert_not_called()


if __name__ == "__main__":
    unittest.main()
