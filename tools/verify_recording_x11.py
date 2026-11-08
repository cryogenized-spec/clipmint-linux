"""Live X11 + bundled FFmpeg smoke test, opt-in CI only.

Actually starts ClipMint's RegionRecorder against an Xvfb-drawn two-color
window, records about two seconds, and checks decoded frame count and pixels.
Not part of normal unittest discovery; no real desktop or user files touched.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from clipmint.capture import RegionRecorder


class PatternWindow(QWidget):
    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(12, 215, 68))
        painter.fillRect(0, 0, self.width() // 2, self.height(),
                         QColor(229, 32, 45))
        painter.fillRect(80, 50, 140, 100, QColor(27, 115, 239))
        painter.end()


class RealX11RecordingTests(unittest.TestCase):
    def test_records_multiframe_nonblack_mp4_with_bundled_ffmpeg(self):
        ffmpeg = Path(os.environ["CLIPMINT_FFMPEG_TEST_BINARY"]).resolve()
        self.assertTrue(ffmpeg.is_file(), f"Missing bundled FFmpeg: {ffmpeg}")
        self.assertTrue(os.environ.get("DISPLAY"), "Xvfb DISPLAY is missing")
        self.assertEqual(os.environ.get("QT_QPA_PLATFORM"), "xcb")

        app = QApplication.instance() or QApplication([])
        window = PatternWindow()
        window.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        window.setGeometry(30, 30, 320, 240)
        window.show()
        window.raise_()
        app.processEvents()
        time.sleep(0.4)
        app.processEvents()

        recorder = RegionRecorder()
        with tempfile.TemporaryDirectory(prefix="clipmint-x11-live-") as tmp:
            folder = Path(tmp)
            with patch("clipmint.capture.ffmpeg_binary", return_value=str(ffmpeg)), \
                 patch("clipmint.capture.recordings_dir", return_value=folder):
                output = recorder.start(
                    QRect(30, 30, 320, 240), "Low", "MP4",
                    pixel_scale=(1.0, 1.0), screen_origin=QPoint(0, 0),
                )
                try:
                    time.sleep(2.35)
                    self.assertTrue(recorder.stop(), "Failed to request MP4 finalize")
                    deadline = time.monotonic() + 12
                    completed = None
                    while time.monotonic() < deadline:
                        completed = recorder.finished()
                        if completed is not None:
                            break
                        app.processEvents()
                        time.sleep(0.1)
                    self.assertIsNotNone(completed, "FFmpeg did not finalize")
                    self.assertEqual(completed[0], 0, "FFmpeg capture process failed")
                    self.assertTrue(output.exists())
                    self.assertGreater(output.stat().st_size, 1500)
                finally:
                    if recorder.process is not None:
                        recorder.stop()
                        recorder.process.terminate()
                        try:
                            recorder.process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            recorder.process.kill()
                            recorder.process.wait(timeout=3)
                        recorder.finished()

            # Decode using the exact same bundled encoder binary and assert
            # frame count, time-on-screen and non-black actual RGB pixels.
            frame_size = 320 * 240
            decoded = subprocess.run(
                [str(ffmpeg), "-hide_banner", "-loglevel", "error",
                 "-i", str(output), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                capture_output=True, timeout=20, check=True,
            )
            self.assertEqual(len(decoded.stdout) % frame_size, 0)
            frames = len(decoded.stdout) // frame_size
            self.assertGreaterEqual(frames, 18, "MP4 contains too few frames")
            first = decoded.stdout[:frame_size]
            self.assertGreater(sum(first) / len(first), 40,
                               "Captured frame is effectively black")
            self.assertGreater(max(first), 120,
                               "Captured pixels do not show our test pattern")

        window.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
