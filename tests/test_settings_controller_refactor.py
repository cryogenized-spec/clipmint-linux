"""Contracts for the extracted Settings page and preference callbacks."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QMessageBox

from clipmint.app import (
    ClipMintWindow, SHORTCUT_SPECS, WheelSafeHistoryLimitComboBox,
)
from clipmint.settings_controller import (
    SettingsControllerMixin, SHORTCUT_SPECS as SETTINGS_SHORTCUT_SPECS,
    WheelSafeHistoryLimitComboBox as SettingsHistoryLimitComboBox,
)


class SettingsControllerRefactorTests(unittest.TestCase):
    def test_main_window_preserves_every_settings_callback(self):
        self.assertTrue(issubclass(ClipMintWindow, SettingsControllerMixin))
        for method in (
            "build_settings_page", "set_clip_labels_visible",
            "set_history_storage_limit", "save_ocr_language",
            "install_shortcuts", "_show_shortcut_value", "change_shortcut",
        ):
            with self.subTest(method=method):
                self.assertIs(
                    getattr(ClipMintWindow, method),
                    getattr(SettingsControllerMixin, method),
                )

    def test_shortcut_and_storage_selector_exports_remain_compatible(self):
        self.assertIs(SHORTCUT_SPECS, SETTINGS_SHORTCUT_SPECS)
        self.assertIs(WheelSafeHistoryLimitComboBox, SettingsHistoryLimitComboBox)

    def test_storage_limit_decline_does_not_prune_or_save(self):
        selector = SimpleNamespace(
            currentData=lambda: 512,
            findData=lambda size: 0 if size == 0 else -1,
            blockSignals=Mock(),
            setCurrentIndex=Mock(),
        )
        settings = SimpleNamespace(value=lambda *args, **kwargs: 0,
                                   setValue=Mock())
        store = SimpleNamespace(max_total_bytes=None, prune_storage_bytes=Mock())
        state = SimpleNamespace(
            history_storage_limit=selector, settings=settings, store=store,
            refresh=Mock(),
        )
        with patch("clipmint.settings_controller.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.No) as question:
            SettingsControllerMixin.set_history_storage_limit(state, 1)
        question.assert_called_once()
        selector.setCurrentIndex.assert_called_once_with(0)
        store.prune_storage_bytes.assert_not_called()
        settings.setValue.assert_not_called()
        state.refresh.assert_not_called()

    def test_clip_labels_preference_only_updates_view(self):
        state = SimpleNamespace(
            settings=SimpleNamespace(setValue=Mock()),
            refresh=Mock(),
        )
        SettingsControllerMixin.set_clip_labels_visible(state, True)
        state.settings.setValue.assert_called_once_with(
            "history/show_clip_labels", True
        )
        state.refresh.assert_called_once()


if __name__ == "__main__":
    unittest.main()
