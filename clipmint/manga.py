"""Render the selected crimson-haired maid illustration as a native, offline Qt asset.

The original user-supplied image was resized for the app; no vector recreation,
external hosting, or runtime file downloads are involved.
"""
from __future__ import annotations

from pathlib import Path
import os
import sys

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


ASSET_NAME = "crimson_maid.png"
FULL_ART_NAME = "kohaku_full.webp"


def _asset_path() -> Path:
    """Prefer full-body Kohaku artwork; preserve the existing portrait fallback.

    The XDG location also permits the user's original artwork to be installed
    without modifying or rebuilding their existing clipboard database.
    """
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    local = base / "clipmint" / FULL_ART_NAME
    if local.is_file():
        return local
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        bundled = Path(frozen_root) / "assets" / "manga" / FULL_ART_NAME
        if bundled.is_file():
            return bundled
        return Path(frozen_root) / "assets" / "manga" / ASSET_NAME
    bundled = Path(__file__).resolve().parent / "assets" / FULL_ART_NAME
    if bundled.is_file():
        return bundled
    return Path(__file__).resolve().parent / "assets" / ASSET_NAME


class CrimsonMaidPortrait(QWidget):
    """Full-body Kohaku illustration, aspect-ratio preserved and never cropped."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.asset_path = _asset_path()
        self.portrait = QPixmap(str(self.asset_path))
        self.setObjectName("crimsonMaidPortrait")
        self.setAccessibleName(
            "Crimson-haired maid, looking over her shoulder with her hands held behind her back"
        )
        self.setToolTip("Kohaku 琥珀 — full-length archive character")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumSize(180, 230)

    def sizeHint(self) -> QSize:
        return QSize(315, 560)

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
            y = content.top() + (content.height() - image_size.height()) // 2
            destination = QRect(x, y, image_size.width(), image_size.height())
            painter.drawPixmap(destination, self.portrait, self.portrait.rect())
        painter.end()
