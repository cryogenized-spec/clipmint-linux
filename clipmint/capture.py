"""Single-display X11 area selection and MP4 screen capture."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import sys

from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


def recordings_dir() -> Path:
    folder = Path.home() / "Videos" / "ClipMint"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def screenshots_dir() -> Path:
    folder = Path.home() / "Pictures" / "ClipMint"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def stamped_filename(prefix: str, suffix: str) -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.{suffix}"


class AreaSelector(QWidget):
    """Draw a rectangle on a screenshot of the primary X11 display."""
    selected = Signal(QRect, QPixmap)
    cancelled = Signal()

    def __init__(self):
        super().__init__(None)
        screen = QApplication.primaryScreen()
        if screen is None:
            raise RuntimeError("No desktop display was detected")
        self.screen_rect = screen.geometry()
        self.background = screen.grabWindow(0)
        if self.background.isNull():
            raise RuntimeError("Cannot capture the desktop; X11 screen grab failed")
        self.anchor: QPoint | None = None
        self.box = QRect()
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(self.screen_rect)
        self.show()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.background)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        if self.box.isValid() and not self.box.isEmpty():
            area = self.box.intersected(self.rect())
            painter.drawPixmap(area, self.background, area)
            painter.setPen(QPen(QColor("#63b6ff"), 2))
            painter.drawRect(area)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.close()
            self.cancelled.emit()
        elif event.button() == Qt.MouseButton.LeftButton:
            self.anchor = event.position().toPoint()
            self.box = QRect(self.anchor, self.anchor)

    def mouseMoveEvent(self, event):
        if self.anchor is not None:
            self.box = QRect(self.anchor, event.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.anchor is None:
            return
        area = QRect(self.anchor, event.position().toPoint()).normalized()
        self.anchor = None
        area = area.intersected(self.rect())
        if area.width() < 10 or area.height() < 10:
            self.close()
            self.cancelled.emit()
            return
        global_area = area.translated(self.screen_rect.topLeft())
        pixels = self.background.copy(area)
        self.hide()
        self.selected.emit(global_area, pixels)
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)


def ffmpeg_binary() -> str:
    """A frozen build uses its bundled FFmpeg and never downloads software."""
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        executable = root / "tools" / "ffmpeg"
        if not executable.is_file():
            raise RuntimeError("This ClipMint package is incomplete (FFmpeg missing).")
        return str(executable)
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("Developer mode: FFmpeg is absent. Use the bundled .deb installer.")
    return executable


class RegionRecorder:
    """Own an FFmpeg subprocess and stop it cleanly through its stdin."""
    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.output: Path | None = None
        self.log = None
        self.stopping = False

    @property
    def active(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, rect: QRect) -> Path:
        if self.process is not None:
            raise RuntimeError("A recording is still running or being finalized")
        if os.environ.get("XDG_SESSION_TYPE", "x11") != "x11":
            raise RuntimeError("Recording currently requires an X11 session")
        ffmpeg_path = ffmpeg_binary()
        display = os.environ.get("DISPLAY")
        if not display:
            raise RuntimeError("DISPLAY is unset; an X11 desktop is required")
        width, height = rect.width() // 2 * 2, rect.height() // 2 * 2
        if width < 10 or height < 10:
            raise RuntimeError("Selected area is too small")
        path = recordings_dir() / stamped_filename("recording", "mp4")
        log_path = path.with_suffix(".ffmpeg.log")
        args = [
            ffmpeg_path, "-hide_banner", "-loglevel", "warning", "-y",
            "-f", "x11grab", "-framerate", "25",
            "-video_size", f"{width}x{height}",
            "-i", f"{display}+{rect.x()},{rect.y()}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "25",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
        ]
        self.log = log_path.open("wb")
        try:
            self.process = subprocess.Popen(
                args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=self.log
            )
        except Exception:
            self.log.close()
            self.log = None
            raise
        self.output = path
        self.stopping = False
        return path

    def stop(self) -> bool:
        if not self.active or self.stopping:
            return False
        self.stopping = True
        try:
            assert self.process is not None and self.process.stdin is not None
            self.process.stdin.write(b"q\n")
            self.process.stdin.flush()
            self.process.stdin.close()
        except (OSError, BrokenPipeError):
            pass
        return True

    def finished(self) -> tuple[int, Path | None] | None:
        if self.process is None:
            return None
        status = self.process.poll()
        if status is None:
            return None
        self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None
        path = self.output
        self.output = None
        self.stopping = False
        return status, path
