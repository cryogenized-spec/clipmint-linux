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

    def __init__(self, parent=None, *, defer_image: bool = False):
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
        # A cold global capture shortcut never reveals the main window.
        # Avoid decoding this large decorative PNG until it is actually painted.
        self._pending_asset = self.asset_path if defer_image else None
        self.card_pixmap = (QPixmap(str(self.asset_path))
                            if self.asset_path and not defer_image else QPixmap())
        self.has_card_art = bool(self.asset_path) if defer_image else not self.card_pixmap.isNull()
        self.setToolTip("Kohaku 琥珀 · The Ephemeral Catch")

    def _load_deferred_art(self):
        if self._pending_asset is None:
            return
        path, self._pending_asset = self._pending_asset, None
        self.card_pixmap = QPixmap(str(path))
        self.has_card_art = not self.card_pixmap.isNull()
        if not self.has_card_art and self.layout() is not None:
            # Retain the original accessible, live text fallback when a PNG
            # that existed during startup is no longer readable at first show.
            self.layout().setContentsMargins(16, 15, 16, 14)
            for index in range(self.layout().count()):
                item = self.layout().itemAt(index)
                if item and item.widget():
                    item.widget().show()

    def paintEvent(self, event):
        self._load_deferred_art()
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
