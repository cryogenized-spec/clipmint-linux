"""The Settings view boundary must preserve public APIs and callbacks."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from clipmint.app import ClipMintWindow, SHORTCUT_SPECS, WheelSafeHistoryLimitComboBox
from clipmint.settings_controller import SettingsControllerMixin
from clipmint.settings_page import (
    SHORTCUT_SPECS as VIEW_SHORTCUT_SPECS,
    WheelSafeHistoryLimitComboBox as ViewHistoryLimitComboBox,
)


class SettingsViewBoundaryTests(unittest.TestCase):
    def test_public_shortcuts_and_wheel_guard_keep_original_identity(self):
        self.assertIs(SHORTCUT_SPECS, VIEW_SHORTCUT_SPECS)
        self.assertIs(WheelSafeHistoryLimitComboBox, ViewHistoryLimitComboBox)
        self.assertTrue(issubclass(ClipMintWindow, SettingsControllerMixin))

    def test_controller_delegates_view_creation_without_mutating_preferences(self):
        state = object()
        with patch("clipmint.settings_controller.build_settings_page") as compose:
            SettingsControllerMixin.build_settings_page(state)
        compose.assert_called_once_with(state)


if __name__ == "__main__":
    unittest.main()
