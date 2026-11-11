"""Native painted Crimson Archive widgets and clipboard row delegate.

The live Qt layout and style sheet remain in crimson_ui.py. These widget
classes are intentionally re-exported there for existing consumers and
tests, without altering object names, painting or accessibility.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QSize, QPoint
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPen, QPolygon,
    QLinearGradient, QBrush, QPainterPath, QFontDatabase,
)
from PySide6.QtWidgets import (
    QWidget, QPushButton, QToolButton, QStyledItemDelegate, QStyle,
)


ROSE = "#FF6780"
LIME = "#C9F473"
PORCELAIN = "#F4EEEB"
MUTED = "#9F949C"
class GothicSearchCapsule(QWidget):
    """Rounded painted search shell independent of native X11 QLineEdit styles."""

    def paintEvent(self, event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r=self.rect().adjusted(1,1,-1,-1)
        fill=QLinearGradient(0,0,self.width(),self.height())
        fill.setColorAt(0,QColor("#2B202D"))
        fill.setColorAt(1,QColor("#211925"))
        p.setPen(QPen(QColor("#985F70"),1.2))
        p.setBrush(QBrush(fill))
        p.drawRoundedRect(r, min(21,r.height()/2), min(21,r.height()/2))
        p.end()


class GothicDivider(QWidget):
    """Subtle line with a central bookplate diamond, matching the reference."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(16)
        self.setAccessibleName("Decorative rose-gold archive divider")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, cy = self.width(), self.height() / 2
        grad = QLinearGradient(0, cy, w, cy)
        for pos, col in ((0, "#46303A"), (.35, "#A76277"),
                         (.5, "#D9A27F"), (.65, "#A76277"), (1, "#46303A")):
            grad.setColorAt(pos, QColor(col))
        p.setPen(QPen(QBrush(grad), 1))
        p.drawLine(QPoint(0, int(cy)), QPoint(w, int(cy)))
        p.setPen(QPen(QColor("#DBA17E"), 1.3))
        diamond = QPolygon([QPoint(w//2,1), QPoint(w//2+7,int(cy)),
                            QPoint(w//2,15), QPoint(w//2-7,int(cy))])
        p.setBrush(QColor("#261820"))
        p.drawPolygon(diamond)
        p.setBrush(QColor("#F3C6A0"))
        p.drawEllipse(QPoint(w//2,int(cy)), 2, 2)
        for x in (w//2-21, w//2+21):
            p.drawEllipse(QPoint(x,int(cy)), 1, 1)
        p.end()


def _footer_title_font_family() -> str:
    """Select the existing app font or its original Georgia fallback."""
    return (
        "Cormorant Garamond"
        if "Cormorant Garamond" in QFontDatabase.families()
        else "Georgia"
    )


class CrimsonFooterButton(QPushButton):
    """Real clickable footer action painted as a lacquered, bevelled plaque."""

    def __init__(self, text: str, primary: bool, parent=None):
        super().__init__(text, parent)
        self.primary = primary
        self._title_font_family: str | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        border = QPainterPath()
        border.moveTo(15, 1)
        border.lineTo(w-7, 1)
        border.quadTo(w-1, 1, w-1, 7)
        border.lineTo(w-1, h-7)
        border.quadTo(w-1,h-1,w-7,h-1)
        border.lineTo(7,h-1)
        border.quadTo(1,h-1,1,h-7)
        border.lineTo(1,16)
        border.closeSubpath()
        fill = QLinearGradient(0,0,0,h)
        if self.primary:
            fill.setColorAt(0, QColor("#A93C58" if self.underMouse() else "#8F2C48"))
            fill.setColorAt(.48, QColor("#77243D"))
            fill.setColorAt(1, QColor("#511D31"))
            edge = QColor("#E37991")
            fg = QColor("#FFF0E2")
        else:
            fill.setColorAt(0, QColor("#FAE8DD" if self.underMouse() else "#EBD4C8"))
            fill.setColorAt(.52, QColor("#E2C8BE"))
            fill.setColorAt(1, QColor("#BA9F9B"))
            edge = QColor("#FCE8DB")
            fg = QColor("#311C29")
        p.setBrush(QBrush(fill))
        p.setPen(QPen(edge, 1.25))
        p.drawPath(border)
        p.setPen(QPen(QColor("#FFFFFF" if not self.primary else "#F7A2AD"), .7))
        p.drawLine(QPoint(17,4), QPoint(w-9,4))
        # Decorative circular command glyph, independent of the title font.
        p.setBrush(fg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPoint(35,h//2), 7 if self.primary else 6, 7 if self.primary else 6)
        p.setPen(fg)
        lines=self.text().split("\n",1)
        display_title = lines[0].replace("●", "").replace("▣", "").strip()
        # Avoid enumerating the system font database on every repaint.
        # Fonts are registered before normal window construction; resolve
        # lazily at the first actual paint, then reuse for hover/focus redraws.
        if self._title_font_family is None:
            self._title_font_family = _footer_title_font_family()
        title_font = QFont(self._title_font_family)
        title_font.setPixelSize(23)
        p.setFont(title_font)
        p.drawText(QRect(56,7,max(5,w-64),26),Qt.AlignmentFlag.AlignVCenter,display_title)
        if len(lines)>1:
            p.setFont(QFont("DejaVu Sans Mono", 10))
            p.drawText(QRect(56,33,max(5,w-64),17),Qt.AlignmentFlag.AlignVCenter,lines[1])
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#FFE3AE"),2))
            p.drawPath(border)
        p.end()


class CrimsonFooterArrow(QToolButton):
    """Split-button arrow retains QMenu selection and keyboard accessibility."""

    def __init__(self, primary: bool, parent=None):
        super().__init__(parent)
        self.primary = primary
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w,h=self.width(),self.height()
        path=QPainterPath()
        path.moveTo(0,1)
        path.lineTo(w-8,1)
        path.quadTo(w-1,1,w-1,8)
        path.lineTo(w-1,h-8)
        path.quadTo(w-1,h-1,w-8,h-1)
        path.lineTo(0,h-1)
        path.closeSubpath()
        grad=QLinearGradient(0,0,0,h)
        if self.primary:
            grad.setColorAt(0,QColor("#9E3450" if self.underMouse() else "#80253F"))
            grad.setColorAt(1,QColor("#4B1B2C"))
        else:
            grad.setColorAt(0,QColor("#EFDBCD" if self.underMouse() else "#DDC2B8"))
            grad.setColorAt(1,QColor("#B39798"))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor("#CA7790" if self.primary else "#F1DED2"),1))
        p.drawPath(path)
        p.setPen(QPen(QColor("#AA6476" if self.primary else "#9A7A82"),1))
        p.drawLine(QPoint(1,5),QPoint(1,h-5))
        p.setPen(QColor("#FAE7DF" if self.primary else "#3B2633"))
        p.setFont(QFont("DejaVu Sans", 13))
        p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,"▾")
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#FFE3AE"),2))
            p.drawPath(path)
        p.end()


def label_type(kind: str, preview: str) -> tuple[str, str, str]:
    if kind == "files":
        return "FILE", "▣", "#DEC3A7"
    if kind == "image":
        return "IMG", "▧", "#D34D70"
    source = preview.strip()
    if source.startswith(("https://", "http://", "www.")):
        return "URL", "⌁", "#91B3B0"
    if source.startswith(("#",)) and len(source) in (4, 7, 9) and all(ch in "0123456789abcdefABCDEF" for ch in source[1:]):
        return "HEX", "#", "#D9B2C9"
    if source.startswith(("sudo ", "def ", "import ", "from ", "apt ", "#!")):
        return "CODE", "</>", "#B9DB76"
    return "TXT", "≡", "#D8D0CE"


def badge_title(kind_tag: str) -> str:
    """Readable rectangular type labels in every history row."""
    return {
        "IMG": "IMAGE", "TXT": "TEXT", "URL": "LINK",
        "FILE": "FILES", "HEX": "HEX", "CODE": "CODE",
    }.get(kind_tag, kind_tag)


class CrimsonClipDelegate(QStyledItemDelegate):
    """Clean clipboard rows: small content icon, primary text, time, pin."""

    def sizeHint(self, option, index):
        return QSize(max(100, option.rect.width()), 77)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = option.rect.adjusted(0, 0, -1, -1)
        active = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        # Restrained card-like rows from the approved Gothic Archive design.
        # The soft enclosure defines a selection without a SaaS-grid appearance.
        bg = QColor("#563044" if active else "#35232E" if hover else "#251B26")
        painter.setBrush(bg)
        painter.setPen(QPen(QColor("#BC7087" if active else "#624353"), 1))
        painter.drawRoundedRect(r.adjusted(4, 3, -4, -3), 7, 7)
        if active:
            painter.fillRect(QRect(r.left()+4, r.top()+9, 3, r.height()-18), QColor("#F1A0AC"))
        meta = index.data(int(Qt.ItemDataRole.UserRole) + 1) or {}
        name = meta.get("preview", index.data(Qt.ItemDataRole.DisplayRole) or "")
        # Classify the original clip, not the optional '[Work]' prefix,
        # otherwise URLs, HEX values and code lose their accurate type chip.
        kind_tag, icon, colour = label_type(
            meta.get("kind", "text"), meta.get("raw_preview", name)
        )
        # Type tags are always visible. The optional setting only controls
        # the extra ornamental content icon and collection prefixes.
        if meta.get("show_badges", False):
            x = r.left() + 12
            y = r.top() + (r.height() - 34) // 2
            painter.setPen(QPen(QColor("#9A5A67"), 1))
            painter.drawRect(x, y, 34, 34)
            painter.setPen(QColor(PORCELAIN))
            painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Weight.Bold))
            painter.drawText(QRect(x, y, 34, 34), Qt.AlignmentFlag.AlignCenter, icon)
            tagx = x + 45
        else:
            tagx = r.left() + 16
        badge = badge_title(kind_tag)
        badge_font = QFont("DejaVu Sans Mono", 9, QFont.Weight.Bold)
        tagw = max(39, QFontMetrics(badge_font).horizontalAdvance(badge) + 14)
        painter.fillRect(QRect(tagx, r.top() + 17, tagw, 19), QColor(colour))
        painter.setPen(QColor("#25101A"))
        painter.setFont(badge_font)
        painter.drawText(
            QRect(tagx, r.top() + 17, tagw, 19),
            Qt.AlignmentFlag.AlignCenter, badge,
        )
        textx = tagx + tagw + 10
        available=max(30, r.right()-textx-40)
        painter.setPen(QColor("#F4EEEB"))
        painter.setFont(QFont("Cormorant Garamond", 17))
        font=QFontMetrics(painter.font())
        painter.drawText(textx, r.top()+29, font.elidedText(name,Qt.TextElideMode.ElideRight,available))
        painter.setFont(QFont("DejaVu Sans Mono", 9))
        painter.setPen(QColor("#CCAFB5"))
        subtitle = meta.get("subtitle", "Image clipboard" if kind_tag=="IMG" else "Text clipboard")
        painter.drawText(textx, r.top()+50,
            QFontMetrics(painter.font()).elidedText(subtitle,Qt.TextElideMode.ElideRight,available+17))
        painter.setPen(QColor("#E3C8C4"))
        painter.drawText(QRect(r.right()-38,r.top()+7,31,17),Qt.AlignmentFlag.AlignRight,meta.get("age",""))
        painter.setPen(QColor("#EFBB8E" if meta.get("pinned") else "#7E6573"))
        painter.drawText(QRect(r.right()-28,r.bottom()-29,19,18),Qt.AlignmentFlag.AlignCenter,"★" if meta.get("pinned") else "☆")
        painter.restore()


