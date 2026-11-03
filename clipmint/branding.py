"""ClipMint's restrained chromatic wordmark and offline DotGothic16 font loader.

Fonts are supplied by the *build system*, not downloaded on a user's desktop.
The UI keeps a safe system-font fallback when running from an unbundled checkout.
"""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QPoint, QSize, Qt, QPointF
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

FONT_FAMILY = "DotGothic16"
FONT_FILE = "DotGothic16-Regular.ttf"
GOTHIC_SERIF = "Cormorant Garamond"
GOTHIC_FILES = ("CormorantGaramond-Regular.ttf", "CormorantGaramond-Italic.ttf")
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

    # Register open-licensed Cormorant Garamond from the frozen installer.
    # Source checkouts remain usable without a bundled copy.
    for name in GOTHIC_FILES:
        locations = []
        if frozen_root:
            locations.append(Path(frozen_root) / "assets" / "fonts" / name)
        locations.append(root / "vendor" / "fonts" / name)
        for location in locations:
            if location.is_file():
                QFontDatabase.addApplicationFont(str(location))
                break

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
    """Paint the logo in book-serif lettering with a rose-gold compass ornament.

    The canvas is actual QPainter geometry and text; there is no asset or web
    dependency. Retain the public name for backwards-compatible UI bindings.
    """

    def __init__(self, family: str, text: str = "CLIPMINT", parent=None):
        super().__init__(parent)
        self.word = text
        available = QFontDatabase.families()
        self.display_font = QFont(GOTHIC_SERIF if GOTHIC_SERIF in available else "Georgia")
        self.display_font.setItalic(True)
        self.display_font.setPixelSize(53)
        self.setAccessibleName("ClipMint")
        self.setAccessibleDescription("ClipMint calligraphy with an eight-point rose-gold star")
        self.setToolTip("ClipMint — local clipboard archive and screen capture")
        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.display_font)
        return QSize(max(280, metrics.horizontalAdvance("ClipMint")+82),
                     max(67, metrics.height()+8))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # Engraved eight-point compass motif with a restrained halo.
        centre = QPointF(32, self.height() / 2 + 1)
        painter.setPen(QPen(QColor("#663345"), 5))
        painter.drawEllipse(centre, 12, 12)
        painter.setPen(QPen(QColor("#DDA080"), 1.3))
        for radius in (22, 12):
            painter.drawLine(QPointF(centre.x()-radius, centre.y()),
                             QPointF(centre.x()+radius, centre.y()))
            painter.drawLine(QPointF(centre.x(), centre.y()-radius),
                             QPointF(centre.x(), centre.y()+radius))
        for radius in (15, 8):
            painter.drawLine(QPointF(centre.x()-radius, centre.y()-radius),
                             QPointF(centre.x()+radius, centre.y()+radius))
            painter.drawLine(QPointF(centre.x()-radius, centre.y()+radius),
                             QPointF(centre.x()+radius, centre.y()-radius))
        painter.setBrush(QColor("#F1C7A5"))
        painter.setPen(QPen(QColor("#BF7082"), 1))
        painter.drawEllipse(centre, 3.1, 3.1)

        painter.setFont(self.display_font)
        x = 65
        font_metrics = QFontMetrics(self.display_font)
        baseline = (self.height()-font_metrics.height())//2 + font_metrics.ascent()
        painter.setPen(QColor("#6A3343"))
        painter.drawText(QPoint(x+1, baseline+2), "ClipMint")
        painter.setPen(QColor("#F9DFCA"))
        painter.drawText(QPoint(x, baseline), "ClipMint")

        # Fine burgundy swoosh gives the engraved wordmark a signature finish.
        painter.setPen(QPen(QColor("#BB5670"), 1.6))
        path = QPainterPath(QPointF(x+77, baseline+4))
        path.cubicTo(x+118,baseline+22, x+179,baseline+19,
                     x+211,baseline+1)
        painter.drawPath(path)
        painter.end()
