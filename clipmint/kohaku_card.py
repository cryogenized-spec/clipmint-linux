"""Kohaku's finished archive card displayed verbatim, not redrawn as vectors.

The image supplied by the user includes the original floral border and caption.
Keep the rest of ClipMint's UI native and interactive. The card is decoration.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QFrame

CARD_ASSET = "kohaku_card.png"


def card_asset_path() -> Path | None:
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    candidates = [base / "clipmint" / CARD_ASSET]
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        candidates.append(Path(frozen) / "assets" / "manga" / CARD_ASSET)
    candidates.append(Path(__file__).resolve().parent / "assets" / CARD_ASSET)
    return next((path for path in candidates if path.is_file()), None)


class KohakuCardFrame(QFrame):
    """One supplied card illustration, aspect-preserved, with no overlay graphics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("maidAlcove")
        self.setAccessibleName("Kohaku 琥珀 — The Ephemeral Catch")
        self.setAccessibleDescription(
            "Crimson-haired maid in a floral gold frame. Japanese verse: "
            "泡沫の如き刹那の思念、悉く我が掌底に封ず。 "
            "Transient thoughts that mimic foam upon the water—"
            "every last one is sealed within the hollow of my palm."
        )
        self.asset_path = card_asset_path()
        self.card_pixmap = QPixmap(str(self.asset_path)) if self.asset_path else QPixmap()
        self.has_card_art = not self.card_pixmap.isNull()
        self.setToolTip("Kohaku 琥珀 · The Ephemeral Catch")

    def paintEvent(self, event):
        if not self.has_card_art:
            # Offline source tree fallback remains a usable ordinary Qt card.
            super().paintEvent(event)
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.fillRect(self.rect(), QColor("#1E111C"))
        scaled = self.card_pixmap.size().scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        p.drawPixmap(x, y, scaled.width(), scaled.height(), self.card_pixmap)
        p.end()
