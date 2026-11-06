"""Single-display X11 area selection and MP4 screen capture."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import sys
from time import monotonic

from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


def physical_rect(rect: QRect, scale_x: float, scale_y: float | None = None) -> QRect:
    """Map logical rectangle *edges* to actual pixels (avoids rounded-size drift).

    Qt selection events and widget geometry use device-independent coordinates.
    QPixmap.copy and FFmpeg x11grab operate on physical pixels.
    """
    from math import isfinite

    if scale_y is None:
        scale_y = scale_x
    if not (isfinite(scale_x) and isfinite(scale_y)
            and scale_x > 0 and scale_y > 0):
        raise ValueError("Invalid capture pixel scale")
    x0, y0 = round(rect.x() * scale_x), round(rect.y() * scale_y)
    x1 = round((rect.x() + rect.width()) * scale_x)
    y1 = round((rect.y() + rect.height()) * scale_y)
    return QRect(x0, y0, max(0, x1 - x0), max(0, y1 - y0))


def global_physical_rect(rect: QRect, scale_x: float, scale_y: float,
                         screen_origin: QPoint) -> QRect:
    """Scale relative to the selected display, then restore its native origin.

    Qt uses device-independent sizes but preserves screen positions in the
    virtual desktop coordinate system; scaling global X/Y directly would move
    captures on an offset primary display.
    """
    local = rect.translated(-screen_origin.x(), -screen_origin.y())
    pixels = physical_rect(local, scale_x, scale_y)
    return pixels.translated(screen_origin)


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
        # The grabbed pixmap is in physical pixels; the selection window and
        # pointer events are in device-independent logical coordinates.
        self.pixel_scale = (
            self.background.width() / self.screen_rect.width(),
            self.background.height() / self.screen_rect.height(),
        )
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
        painter.fillRect(self.rect(), QColor(0, 0, 0, 64))
        if self.box.isValid() and not self.box.isEmpty():
            area = self.box.intersected(self.rect())
            source_pixels = physical_rect(area, *self.pixel_scale)
            painter.drawPixmap(area, self.background, source_pixels)
            painter.setPen(QPen(QColor("#C94A62"), 2))
            painter.drawRect(area)
            painter.setPen(QColor("#F1F5F9"))
            size_label = f"{source_pixels.width()} × {source_pixels.height()} px"
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
        pixels = self.background.copy(physical_rect(area, *self.pixel_scale))
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

    # The UI polls finished() every 300 ms. Never block the Qt thread waiting
    # for FFmpeg: request a clean MP4 trailer, then escalate only if it hangs.
    STOP_GRACE_SECONDS = 5.0
    TERMINATE_GRACE_SECONDS = 2.0

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
        self.stop_requested_at: float | None = None
        self.terminate_sent_at: float | None = None
        self.kill_sent = False
        self.format = "MP4"
        self.quality = "High"
        self.estimated_bytes_per_second = 450_000

    @property
    def active(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, rect: QRect, quality: str = "High", file_format: str = "MP4",
              pixel_scale: tuple[float, float] | None = None,
              screen_origin: QPoint | None = None) -> Path:
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
        screen = QApplication.primaryScreen()
        if pixel_scale is None:
            ratio = screen.devicePixelRatio() if screen is not None else 1.0
            pixel_scale = (ratio, ratio)
        if screen_origin is None:
            screen_origin = screen.geometry().topLeft() if screen is not None else QPoint()
        capture = global_physical_rect(rect, *pixel_scale, screen_origin)
        width, height = capture.width() // 2 * 2, capture.height() // 2 * 2
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
            "-i", f"{display}+{capture.x()},{capture.y()}",
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
        self.stop_requested_at = None
        self.terminate_sent_at = None
        self.kill_sent = False
        return path

    def stop(self) -> bool:
        if not self.active or self.stopping:
            return False
        self.stopping = True
        self.stop_requested_at = monotonic()
        try:
            assert self.process is not None and self.process.stdin is not None
            self.process.stdin.write(b"q\n")
            self.process.stdin.flush()
            self.process.stdin.close()
        except (OSError, BrokenPipeError, ValueError):
            # A closed pipe can mean FFmpeg has already exited; polling will
            # collect its exit status or escalate without freezing the UI.
            pass
        return True

    def finished(self) -> tuple[int, Path | None] | None:
        """Nonblocking poll with bounded graceful shutdown for stalled FFmpeg."""
        if self.process is None:
            return None
        status = self.process.poll()
        if status is None:
            if self.stopping and self.stop_requested_at is not None:
                now = monotonic()
                if (self.terminate_sent_at is None
                        and now - self.stop_requested_at >= self.STOP_GRACE_SECONDS):
                    try:
                        self.process.terminate()
                    except ProcessLookupError:
                        pass
                    self.terminate_sent_at = now
                elif (self.terminate_sent_at is not None
                      and not self.kill_sent
                      and now - self.terminate_sent_at >= self.TERMINATE_GRACE_SECONDS):
                    try:
                        self.process.kill()
                    except ProcessLookupError:
                        pass
                    self.kill_sent = True
            return None
        self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None
        path = self.output
        self.output = None
        self.stopping = False
        self.stop_requested_at = None
        self.terminate_sent_at = None
        self.kill_sent = False
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
