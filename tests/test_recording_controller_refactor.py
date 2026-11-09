"""Contract tests for the split recorder controller without starting FFmpeg.

The refactor must preserve every public window callback and keep the recorder's
ownership and UI enabled-state transitions identical to the original class.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from clipmint.app import ClipMintWindow
from clipmint.recording_controller import RecordingControllerMixin


class RecordingControllerExtractionTests(unittest.TestCase):
    def test_window_inherits_all_original_recorder_callbacks(self):
        self.assertTrue(issubclass(ClipMintWindow, RecordingControllerMixin))
        for name in (
            "offer_pending_recordings", "choose_recording", "start_video",
            "show_recorder", "cancel_recorder", "launch_recorder",
            "stop_recording", "poll_recording", "update_buttons",
        ):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(ClipMintWindow, name),
                    getattr(RecordingControllerMixin, name),
                )

    def test_format_selection_keeps_original_area_selection_callback(self):
        state = SimpleNamespace(select_area=Mock(), capture_format=None)
        RecordingControllerMixin.choose_recording(state, "GIF")
        self.assertEqual(state.capture_format, "GIF")
        state.select_area.assert_called_once_with("video")
        RecordingControllerMixin.choose_recording(state, "invalid")
        self.assertEqual(state.capture_format, "MP4")

    def test_launch_forwards_scale_origin_and_does_not_block_ui(self):
        outfile = Path("/tmp/clipmint-refactor-recording.mp4")
        recorder = SimpleNamespace(
            start=Mock(return_value=outfile),
            estimated_bytes_per_second=175_000,
        )
        popup = SimpleNamespace(recording_started=Mock())
        state = SimpleNamespace(
            recorder=recorder,
            recorder_window=popup,
            capture_rect=object(),
            capture_scale=(1.5, 1.5),
            capture_origin=object(),
            update_buttons=Mock(),
        )
        RecordingControllerMixin.launch_recorder(state, "High", "MP4")
        recorder.start.assert_called_once_with(
            state.capture_rect, "High", "MP4",
            pixel_scale=state.capture_scale,
            screen_origin=state.capture_origin,
        )
        popup.recording_started.assert_called_once_with(outfile, 175_000)
        state.update_buttons.assert_called_once_with()

    def test_failed_launch_preserves_popup_and_reenables_start(self):
        recorder = SimpleNamespace(
            start=Mock(side_effect=RuntimeError("no X11 display")),
        )
        popup = SimpleNamespace(start_failed=Mock())
        state = SimpleNamespace(
            recorder=recorder,
            recorder_window=popup,
            capture_rect=object(),
            capture_scale=None,
            capture_origin=None,
            error=Mock(),
        )
        RecordingControllerMixin.launch_recorder(state, "Low", "MP4")
        popup.start_failed.assert_called_once_with()
        state.error.assert_called_once_with("Recording", "no X11 display")

    def test_stopping_recorder_keeps_nonblocking_finalize_flow(self):
        state = SimpleNamespace(
            recorder=SimpleNamespace(stop=Mock(return_value=True)),
            statusBar=Mock(),
            inform=Mock(),
            update_buttons=Mock(),
        )
        RecordingControllerMixin.stop_recording(state)
        state.statusBar.return_value.showMessage.assert_called_once()
        state.inform.assert_not_called()
        state.update_buttons.assert_called_once_with()

    def test_pending_recovery_never_runs_during_shutdown(self):
        state = SimpleNamespace(
            _closing=True, recorder=SimpleNamespace(process=None)
        )
        RecordingControllerMixin.offer_pending_recordings(state)


if __name__ == "__main__":
    unittest.main()
