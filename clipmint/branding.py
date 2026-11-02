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
    """Kohaku-era ClipMint mark: elegant parchment serif, ornamental star.

    Retain the public class name for backwards compatibility with existing
    UI bindings; this is genuine Qt text/geometry, not an image.
    """

    def __init__(self, family: str, text: str = "CLIPMINT", parent=None):
        super().__init__(parent)
        self.word = text
        self.display_font = QFont("Georgia")
        self.display_font.setItalic(True)
        self.display_font.setPixelSize(43)
        self.setAccessibleName("ClipMint")
        self.setAccessibleDescription("ClipMint written in elegant ivory calligraphy")
        self.setToolTip("ClipMint — clipboard and screen capture")
        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.display_font)
        return QSize(max(205, metrics.horizontalAdvance("ClipMint")+58),
                     max(55, metrics.height()+10))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        center = QPointF(23, self.height()/2)
        p.setPen(QPen(QColor("#EAA48B"), 1.25))
        for delta in (15, 9):
            p.drawLine(QPointF(center.x()-delta,center.y()),
                       QPointF(center.x()+delta,center.y()))
            p.drawLine(QPointF(center.x(),center.y()-delta),
                       QPointF(center.x(),center.y()+delta))
        p.drawLine(QPointF(center.x()-8,center.y()-8),
                   QPointF(center.x()+8,center.y()+8))
        p.drawLine(QPointF(center.x()-8,center.y()+8),
                   QPointF(center.x()+8,center.y()-8))
        p.setFont(self.display_font)
        p.setPen(QColor("#F3DECD"))
        x = 46
        font_metrics = QFontMetrics(self.display_font)
        baseline = (self.height()-font_metrics.height())//2+font_metrics.ascent()
        p.drawText(QPoint(x, baseline), "ClipMint")
        # A restrained hand-inked flourish below the serif.
        p.setPen(QPen(QColor("#AA4963"), 1.35))
        path = QPainterPath(QPointF(x+88,baseline+7))
        path.cubicTo(x+116,baseline+18, x+145,baseline+15,
                     x+170,baseline+1)
        p.drawPath(path)
        p.end()
