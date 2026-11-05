"""Regression tests for nonblocking FFmpeg shutdown in the Qt recording poll."""
import unittest
from pathlib import Path
from unittest.mock import patch

from clipmint.capture import RegionRecorder


class FakeStdin:
    def __init__(self):
        self.writes = []
        self.closed = False

    def write(self, data):
        self.writes.append(data)

    def flush(self):
        pass

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self):
        self.stdin = FakeStdin()
        self.exit_status = None
        self.terminations = 0
        self.kills = 0

    def poll(self):
        return self.exit_status

    def terminate(self):
        self.terminations += 1

    def kill(self):
        self.kills += 1


class RecorderShutdownTests(unittest.TestCase):
    def setUp(self):
        self.recorder = RegionRecorder()
        self.process = FakeProcess()
        self.recorder.process = self.process
        self.recorder.output = Path("/tmp/clipmint-test-recording.mp4")

    def test_clean_exit_keeps_normal_save_flow(self):
        with patch("clipmint.capture.monotonic", return_value=100.0):
            self.assertTrue(self.recorder.stop())
        self.assertEqual(self.process.stdin.writes, [b"q\n"])
        self.assertTrue(self.process.stdin.closed)
        self.assertFalse(self.recorder.stop())
        self.process.exit_status = 0
        self.assertEqual(
            self.recorder.finished(), (0, Path("/tmp/clipmint-test-recording.mp4"))
        )
        self.assertEqual(self.process.terminations, 0)
        self.assertEqual(self.process.kills, 0)
        self.assertIsNone(self.recorder.process)
        self.assertFalse(self.recorder.stopping)
        self.assertIsNone(self.recorder.stop_requested_at)

    def test_stalled_ffmpeg_is_terminated_then_killed_without_blocking(self):
        with patch("clipmint.capture.monotonic", return_value=100.0):
            self.assertTrue(self.recorder.stop())
        for now in (101.0, 104.9):
            with patch("clipmint.capture.monotonic", return_value=now):
                self.assertIsNone(self.recorder.finished())
        self.assertEqual(self.process.terminations, 0)
        with patch("clipmint.capture.monotonic", return_value=105.0):
            self.assertIsNone(self.recorder.finished())
        self.assertEqual(self.process.terminations, 1)
        with patch("clipmint.capture.monotonic", return_value=106.9):
            self.assertIsNone(self.recorder.finished())
        self.assertEqual(self.process.kills, 0)
        with patch("clipmint.capture.monotonic", return_value=107.0):
            self.assertIsNone(self.recorder.finished())
        self.assertEqual(self.process.kills, 1)
        with patch("clipmint.capture.monotonic", return_value=110.0):
            self.assertIsNone(self.recorder.finished())
        self.assertEqual(self.process.kills, 1)
        self.process.exit_status = -9
        self.assertEqual(self.recorder.finished()[0], -9)
        self.assertFalse(self.recorder.stopping)

    def test_recording_does_not_timeout_without_a_stop_request(self):
        with patch("clipmint.capture.monotonic", return_value=1_000.0):
            self.assertIsNone(self.recorder.finished())
        self.assertEqual(self.process.terminations, 0)
        self.assertEqual(self.process.kills, 0)


if __name__ == "__main__":
    unittest.main()
