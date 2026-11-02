"""Display ClipMint's original generated manga portrait, not a vector redraw.

The binary JPEG is an offline app asset. The character illustration is
decorative and cannot intercept clicks or take keyboard focus.
"""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


def _asset_path() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "assets" / "manga" / "koma_manga.jpg"
    return Path(__file__).resolve().parent / "assets" / "koma_manga.jpg"


class KomaMascot(QWidget):
    """An intentionally unobtrusive crop of the *actual* inked manga asset."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.asset_path = _asset_path()
        self.portrait = QPixmap(str(self.asset_path))
        self.setObjectName("komaMascot")
        self.setAccessibleName("Koma — original pink-and-lime manga archivist portrait")
        self.setToolTip("Koma / コマ — ClipMint's paper archivist")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        return QSize(160, 172)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if not self.portrait.isNull():
            # Show face/headphones and a little jacket at actual sidebar scale.
            # The full portrait JPEG remains embedded and unmodified in the app.
            source_width = self.portrait.width()
            source_height = min(
                self.portrait.height(),
                round(source_width * self.height() / max(self.width(), 1)),
            )
            source = QRect(0, 0, source_width, source_height)
            painter.drawPixmap(self.rect(), self.portrait, source)
        else:
            painter.setPen(QColor("#F1F5F9"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "KOMA / ART UNAVAILABLE"
            )
        painter.end()
