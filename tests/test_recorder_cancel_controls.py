"""Recorder cancel restores the main window controls without starting FFmpeg."""
from __future__ import annotations

import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from clipmint.app import ClipMintWindow


class RecorderCancelTests(unittest.TestCase):
    @staticmethod
    def window(process=None):
        # Use the production state transition methods without opening a Qt
        # window or touching real screenshot/recording hardware.
        state = SimpleNamespace(
            recorder=SimpleNamespace(process=process),
            recorder_window=object(),
            record_button=Mock(),
            record_menu=Mock(),
            tray_stop=None,
            show_window=Mock(),
        )
        state.update_buttons = lambda: ClipMintWindow.update_buttons(state)
        return state

    def test_cancel_before_start_restores_main_recording_controls(self):
        state = self.window()
        ClipMintWindow.cancel_recorder(state)
        self.assertIsNone(state.recorder_window)
        state.record_button.setEnabled.assert_called_once_with(True)
        state.record_menu.setEnabled.assert_called_once_with(True)
        state.show_window.assert_called_once_with()

    def test_cancel_does_not_reset_controls_during_active_recording(self):
        state = self.window(process=object())
        initial_recorder_window = state.recorder_window
        ClipMintWindow.cancel_recorder(state)
        self.assertIs(state.recorder_window, initial_recorder_window)
        state.record_button.setEnabled.assert_not_called()
        state.record_menu.setEnabled.assert_not_called()
        state.show_window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
