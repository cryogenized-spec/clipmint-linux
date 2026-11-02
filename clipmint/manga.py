"""Render the selected crimson-haired maid illustration as a native, offline Qt asset.

The original user-supplied image was resized for the app; no vector recreation,
external hosting, or runtime file downloads are involved.
"""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


ASSET_NAME = "crimson_maid.png"


def _asset_path() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "assets" / "manga" / ASSET_NAME
    return Path(__file__).resolve().parent / "assets" / ASSET_NAME


class CrimsonMaidPortrait(QWidget):
    """A decorative crop of the actual character artwork, not a redrawn mascot."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.asset_path = _asset_path()
        self.portrait = QPixmap(str(self.asset_path))
        self.setObjectName("crimsonMaidPortrait")
        self.setAccessibleName(
            "Crimson-haired maid, looking over her shoulder with her hands held behind her back"
        )
        self.setToolTip("ClipMint character artwork / メイド")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumSize(180, 230)

    def sizeHint(self) -> QSize:
        return QSize(310, 440)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if self.portrait.isNull():
            painter.setPen(QColor("#F4EEEB"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "ART UNAVAILABLE")
        else:
            # Approved v2 composition: show the entire original portrait.
            # Never stretch, truncate its hair or apply a synthetic background.
            content = self.rect().adjusted(0, 0, 0, 0)
            image_size = self.portrait.size().scaled(
                content.size(), Qt.AspectRatioMode.KeepAspectRatio
            )
            x = content.center().x() - image_size.width() // 2
            y = content.bottom() - image_size.height() + 1
            destination = QRect(x, y, image_size.width(), image_size.height())
            painter.drawPixmap(destination, self.portrait, self.portrait.rect())
        painter.end()
