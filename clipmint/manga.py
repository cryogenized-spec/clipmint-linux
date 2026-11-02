"""Small original ink illustration for ClipMint's sidebar.

The illustration is ornamental and is never allowed to intercept pointer input.
The asset ships inside the offline installer; missing assets fail gracefully.
"""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget


def _asset_path() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "assets" / "manga" / "koma.svg"
    return Path(__file__).resolve().parent / "assets" / "koma.svg"


class KomaMascot(QWidget):
    """A small manga-panel portrait with no controls or interaction."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = QSvgRenderer(str(_asset_path()), self)
        self.setObjectName("komaMascot")
        self.setAccessibleName("Koma — original manga paper archivist illustration")
        self.setToolTip("Koma / コマ — ClipMint's paper archivist")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        return QSize(149, 157)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.renderer.isValid():
            self.renderer.render(painter, QRectF(self.rect()))
        else:
            painter.setPen(QColor("#F1F5F9"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "KOMA / 01")
        painter.end()
