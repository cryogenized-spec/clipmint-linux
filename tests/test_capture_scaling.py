"""Pixel-exact X11 screenshot/recording selection at scaled Qt densities."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QRect, QPoint
from PySide6.QtGui import QColor, QPixmap, QPainter
from PySide6.QtWidgets import QApplication

from clipmint.capture import RegionRecorder, physical_rect, global_physical_rect


class ScaledCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A QPixmap needs a Qt application, even on an offscreen CI display.
        cls.app = QApplication.instance() or QApplication([])

    def test_rectangles_at_100_150_and_200_percent(self):
        logical = QRect(20, 30, 100, 80)
        for factor, expected in (
            (1.0, QRect(20, 30, 100, 80)),
            (1.5, QRect(30, 45, 150, 120)),
            (2.0, QRect(40, 60, 200, 160)),
        ):
            with self.subTest(scale=factor):
                self.assertEqual(physical_rect(logical, factor), expected)

    def test_nonzero_screen_origin_is_not_scaled(self):
        origin = QPoint(1920, 0)
        logical = QRect(1940, 30, 100, 80)
        self.assertEqual(
            global_physical_rect(logical, 1.5, 1.5, origin),
            QRect(1950, 45, 150, 120),
        )

    def test_nonintegral_edges_are_converted_once(self):
        logical = QRect(7, 11, 13, 19)
        scaled = physical_rect(logical, 1.5)
        self.assertEqual(scaled.right() + 1, round(20 * 1.5))
        self.assertEqual(scaled.bottom() + 1, round(30 * 1.5))
        self.assertEqual(scaled.x(), round(7 * 1.5))
        self.assertEqual(scaled.y(), round(11 * 1.5))

    def test_screenshot_copy_uses_physical_region(self):
        source = QPixmap(400, 320)
        source.fill(QColor("red"))
        painter = QPainter(source)
        painter.fillRect(QRect(40, 60, 200, 160), QColor("green"))
        painter.end()
        cropped = source.copy(physical_rect(QRect(20, 30, 100, 80), 2.0))
        self.assertEqual((cropped.width(), cropped.height()), (200, 160))
        self.assertEqual(cropped.toImage().pixelColor(100, 70), QColor("green"))

    def test_ffmpeg_uses_physical_coordinates_without_moving_ui_region(self):
        logical = QRect(20, 30, 100, 80)
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"DISPLAY": ":99", "XDG_SESSION_TYPE": "x11"}
        ), patch("clipmint.capture.recordings_dir", return_value=Path(directory)), patch(
            "clipmint.capture.ffmpeg_binary", return_value="/usr/bin/ffmpeg"
        ), patch("clipmint.capture.subprocess.Popen") as popen:
            popen.return_value = Mock()
            recorder = RegionRecorder()
            recorder.start(logical, "High", "MP4", pixel_scale=(1.5, 1.5))
            args = popen.call_args.args[0]
            self.assertEqual(args[args.index("-video_size") + 1], "150x120")
            self.assertEqual(args[args.index("-i") + 1], ":99+30,45")
            self.assertEqual(logical, QRect(20, 30, 100, 80))
            recorder.log.close()
            recorder.log = None

    def test_ffmpeg_uses_native_origin_on_offset_display(self):
        logical = QRect(1940, 30, 100, 80)
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"DISPLAY": ":99", "XDG_SESSION_TYPE": "x11"}
        ), patch("clipmint.capture.recordings_dir", return_value=Path(directory)), patch(
            "clipmint.capture.ffmpeg_binary", return_value="/usr/bin/ffmpeg"
        ), patch("clipmint.capture.subprocess.Popen") as popen:
            popen.return_value = Mock()
            recorder = RegionRecorder()
            recorder.start(
                logical, "High", "MP4", pixel_scale=(1.5, 1.5),
                screen_origin=QPoint(1920, 0),
            )
            args = popen.call_args.args[0]
            self.assertEqual(args[args.index("-video_size") + 1], "150x120")
            self.assertEqual(args[args.index("-i") + 1], ":99+1950,45")
            recorder.log.close()
            recorder.log = None


if __name__ == "__main__":
    unittest.main()
