"""ClipMint's restrained chromatic wordmark and offline DotGothic16 font loader.

Fonts are supplied by the *build system*, not downloaded on a user's desktop.
The UI keeps a safe system-font fallback when running from an unbundled checkout.
"""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

FONT_FAMILY = "DotGothic16"
FONT_FILE = "DotGothic16-Regular.ttf"
PINK = QColor("#FF5AB3")
LIME = QColor("#B9FF45")
WHITE = QColor("#F1F5F9")


def register_display_font() -> str:
    """Load the bundled OFL font (or an installed copy), without network access."""
    root = Path(__file__).resolve().parent.parent
    candidates = []
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.append(Path(frozen_root) / "assets" / "fonts" / FONT_FILE)
    candidates.append(root / "vendor" / "fonts" / FONT_FILE)

    for candidate in candidates:
        if not candidate.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(candidate))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if FONT_FAMILY in families:
                return FONT_FAMILY
            if families:
                return families[0]
    if FONT_FAMILY in QFontDatabase.families():
        return FONT_FAMILY
    return "DejaVu Sans Mono"


class ChromaticWordmark(QWidget):
    """Hand-registered three-pass type, not a generic glow or CSS shadow.

    Use the expressive treatment only for the brand. Ordinary controls stay
    single-colour and legible. The offsets resemble imperfect screen printing.
    """

    def __init__(self, family: str, text: str = "CLIPMINT", parent=None):
        super().__init__(parent)
        self.word = text
        self.display_font = QFont(family)
        self.display_font.setPixelSize(32)
        self.display_font.setWeight(QFont.Weight.Normal)
        self.setAccessibleName("ClipMint")
        self.setAccessibleDescription("Pink, lime and white misregistered pixel wordmark")
        self.setToolTip("ClipMint — clipboard and screen capture")
        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.display_font)
        return QSize(metrics.horizontalAdvance(self.word) + 14, max(46, metrics.height() + 12))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self.display_font)
        metrics = QFontMetrics(self.display_font)
        baseline = (self.height() - metrics.height()) // 2 + metrics.ascent()
        origin = QPoint(5, baseline)

        # Uneven offsets, deliberately more like screen-print registration
        # than symmetric neon text-shadow.
        for offset, colour in (
            (QPoint(-2, 2), PINK),
            (QPoint(2, -1), LIME),
            (QPoint(0, 0), WHITE),
        ):
            painter.setPen(colour)
            painter.drawText(origin + offset, self.word)

        painter.end()
