"""Render the *real Qt app* on its Screenshots page with synthetic local PNGs.

Only for CI/review. The fake captures contain no user data or real credentials.
Usage: QT_QPA_PLATFORM=offscreen python tools/render_screenshot_gallery_review.py out.png
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from clipmint.app import ClipMintWindow


def fake_capture(target: Path, heading: str, accent: str) -> None:
    image = QImage(1200, 675, QImage.Format.Format_RGB32)
    image.fill(QColor("#151821"))
    painter = QPainter(image)
    painter.fillRect(QRect(0, 0, 1200, 64), QColor("#262836"))
    painter.fillRect(QRect(0, 64, 190, 611), QColor("#1C2433"))
    painter.setPen(QColor("#EEF0EE"))
    painter.setFont(QFont("DejaVu Sans", 26))
    painter.drawText(QRect(225, 90, 940, 60), Qt.AlignmentFlag.AlignLeft, heading)
    painter.setFont(QFont("DejaVu Sans", 11))
    painter.drawText(QRect(225, 140, 940, 35), Qt.AlignmentFlag.AlignLeft,
                     "SYNTHETIC PREVIEW - NO REAL SCREEN CONTENT")
    for row in range(3):
        for col in range(3):
            x = 225 + col * 305
            y = 208 + row * 134
            painter.fillRect(QRect(x, y, 270, 109), QColor("#303548"))
            painter.fillRect(QRect(x + 15, y + 15, 35, 70), QColor(accent))
            painter.fillRect(QRect(x + 62, y + 22, 175, 10), QColor("#6B7489"))
            painter.fillRect(QRect(x + 62, y + 50, 137, 9), QColor("#48566E"))
    painter.end()
    if not image.save(str(target), "PNG"):
        raise RuntimeError("Could not write synthetic PNG fixture")


def main(destination: Path) -> None:
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as root:
        base = Path(root)
        shots = base / "shots"
        recordings = base / "videos"
        shots.mkdir()
        recordings.mkdir()
        os.environ["XDG_DATA_HOME"] = str(base)
        fake_capture(shots / "Screenshot - Dashboard.png", "Dashboard / Demo", "#BD5876")
        fake_capture(shots / "Screenshot - Workshop.png", "Workshop / Demo", "#DCA37E")
        fake_capture(shots / "Screenshot - Project.png", "Projects / Demo", "#8DAFA0")
        with patch("clipmint.app.screenshots_dir", return_value=shots), \
             patch("clipmint.app.recordings_dir", return_value=recordings):
            window = ClipMintWindow()
            try:
                window.resize(1507, 1044)
                window.show()
                window.open_section(1)
                for _ in range(4):
                    app.processEvents()
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not window.grab().save(str(destination), "PNG"):
                    raise RuntimeError("Qt screenshot grab failed")
            finally:
                window.poller.stop()
                window.store.close()
                window.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: render_screenshot_gallery_review.py output.png")
    main(Path(sys.argv[1]).resolve())
