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
    """Interactive region selection with a visible noncaptured instruction banner."""
    selected = Signal(QRect, QPixmap)
    cancelled = Signal()

    def __init__(self, purpose: str = "image"):
        super().__init__(None)
        self.purpose = purpose
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
            painter.setPen(QPen(QColor("#00FF9D"), 2))
            painter.drawRect(area)
            painter.setPen(QColor("#F1F5F9"))
            size_label = f"{area.width()} × {area.height()} px"
            size_box = QRect(area.left() + 5, max(65, area.top() - 32), 160, 26)
            painter.fillRect(size_box, QColor("#0D131F"))
            painter.drawText(size_box, Qt.AlignmentFlag.AlignCenter, size_label)
        # This is painted over the pre-captured desktop image and is not part of
        # the screenshot/recording source. Instructions remain visible while dragging.
        hint = ("SCREENSHOT" if self.purpose == "image" else "VIDEO")
        message = (
            f"{hint}  •  Click and drag to select the capture area.  "
            "Release to confirm.  Esc / right-click to cancel."
        )
        painter.setPen(Qt.PenStyle.NoPen)
        guide = QRect(16, 14, min(max(0, self.width() - 32), 740), 45)
        if guide.width() > 0:
            painter.setBrush(QColor("#0D131F"))
            painter.drawRoundedRect(guide, 9, 9)
            painter.setPen(QColor("#F1F5F9"))
            painter.drawText(
                guide.adjusted(12, 0, -12, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                message,
            )
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
    """FFmpeg X11 recorder. Captures to a temporary file until user confirms saving."""

    QUALITY = {
        "High": (30, 20, 450_000),
        "Medium": (25, 25, 230_000),
        "Low": (15, 30, 110_000),
    }

    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.output: Path | None = None
        self.log = None
        self.stopping = False
        self.format = "MP4"
        self.quality = "High"
        self.estimated_bytes_per_second = 450_000

    @property
    def active(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, rect: QRect, quality: str = "High", file_format: str = "MP4") -> Path:
        if self.process is not None:
            raise RuntimeError("A previous recording is still running or finalizing")
        if os.environ.get("XDG_SESSION_TYPE", "x11").lower() != "x11":
            raise RuntimeError("Screen recording requires X11")
        ffmpeg_path = ffmpeg_binary()
        display = os.environ.get("DISPLAY")
        if not display:
            raise RuntimeError("DISPLAY is unset; an X11 desktop is required")
        if quality not in self.QUALITY or file_format not in ("MP4", "GIF"):
            raise ValueError("Unsupported recording options")
        width, height = rect.width() // 2 * 2, rect.height() // 2 * 2
        if width < 10 or height < 10:
            raise RuntimeError("Selected area is too small")
        rate, crf, byte_rate = self.QUALITY[quality]
        self.format, self.quality = file_format, quality
        self.estimated_bytes_per_second = byte_rate * (2.5 if file_format == "GIF" else 1)
        suffix = "mp4" if file_format == "MP4" else "gif"
        # Filename starts with a dot to hide unfinished captures from ordinary file browsers.
        path = recordings_dir() / stamped_filename(".pending-recording", suffix)
        log_path = path.with_suffix(".ffmpeg.log")
        args = [
            ffmpeg_path, "-hide_banner", "-loglevel", "warning", "-y",
            "-f", "x11grab", "-framerate", str(rate),
            "-video_size", f"{width}x{height}",
            "-i", f"{display}+{rect.x()},{rect.y()}",
        ]
        if file_format == "MP4":
            args += ["-c:v", "libx264", "-preset", "ultrafast",
                     "-crf", str(crf), "-pix_fmt", "yuv420p",
                     "-movflags", "+faststart"]
        else:
            # GIF has no audio, uses a bounded frame rate to constrain file sizes.
            gif_rate = {"High": 15, "Medium": 12, "Low": 8}[quality]
            args += ["-vf", f"fps={gif_rate},scale=iw:-1:flags=lanczos", "-f", "gif"]
        args.append(str(path))
        self.log = log_path.open("wb")
        try:
            self.process = subprocess.Popen(
                args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log
            )
        except Exception:
            self.log.close()
            self.log = None
            log_path.unlink(missing_ok=True)
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

    @staticmethod
    def resolve(path: Path, keep: bool) -> Path | None:
        """Save or discard a finished recording; never remove it before ffmpeg exits."""
        log = path.with_suffix(".ffmpeg.log")
        if not keep:
            path.unlink(missing_ok=True)
            log.unlink(missing_ok=True)
            return None
        destination = recordings_dir() / stamped_filename("recording", path.suffix.lstrip("."))
        path.rename(destination)
        log.unlink(missing_ok=True)
        return destination
