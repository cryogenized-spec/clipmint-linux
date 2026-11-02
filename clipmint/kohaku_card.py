"""Kohaku's native Qt ornamental archive card.

All geometry is painted in Qt; this is not a flat mockup image. The frame
scales with the panel, and its decoration never intercepts pointer events.
"""
from __future__ import annotations

import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame


class KohakuCardFrame(QFrame):
    """Arcane card frame, with fine rose-gold filigree and floral ring."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("maidAlcove")
        self.setAccessibleName("Kohaku — 琥珀, archival character card")

    @staticmethod
    def _ornament(p: QPainter, x: float, y: float, sx: int, sy: int):
        """Symmetric, thin filigree corner scrolls."""
        p.save()
        p.translate(x, y)
        p.scale(sx, sy)
        p.setPen(QPen(QColor("#D9A16F"), 1.15))
        for offset in (0, 4):
            path = QPainterPath(QPointF(8 + offset, 42))
            path.cubicTo(7 + offset, 20, 11, 11, 35, 8 + offset)
            path.cubicTo(28, 18, 16, 17, 18, 34)
            path.cubicTo(25, 29, 35, 16, 45, 15)
            path.cubicTo(54, 16, 55, 22, 46, 26)
            p.drawPath(path)
        for xx, yy in ((11, 11), (34, 9), (12, 37), (41, 24)):
            p.drawLine(QPointF(xx-3, yy), QPointF(xx+3, yy))
            p.drawLine(QPointF(xx, yy-3), QPointF(xx, yy+3))
        p.restore()

    @staticmethod
    def _blossom(p: QPainter, x: float, y: float, size: float, opacity: int):
        petal = QColor("#D35A79")
        petal.setAlpha(opacity)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(petal)
        for a in range(5):
            angle = 2 * math.pi * a / 5
            p.drawEllipse(QPointF(x + math.cos(angle)*size*.85,
                                   y + math.sin(angle)*size*.85),
                          size*.63, size*.63)
        p.setBrush(QColor("#E5B78C"))
        p.drawEllipse(QPointF(x,y), size*.27, size*.27)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        r = self.rect().adjusted(2, 2, -3, -3)

        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0.0, QColor("#311524"))
        g.setColorAt(0.43, QColor("#220F1D"))
        g.setColorAt(1.0, QColor("#170F1D"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, 4, 4)

        # Fine outer and inner border, precise enough at both compact and large sizes.
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#AD6B65"), 1.35))
        p.drawRoundedRect(r, 3, 3)
        p.setPen(QPen(QColor("#6A3748"), .8))
        p.drawRoundedRect(r.adjusted(5, 5, -5, -5), 2, 2)

        for x, y, sx, sy in (
            (0, 0, 1, 1), (w, 0, -1, 1), (0, h, 1, -1),
            (w, h, -1, -1)
        ):
            self._ornament(p, x, y, sx, sy)

        # Lunar/arcane rings sit BEHIND the original character artwork.
        ring_height = min(max(150, h * .60), w * 1.02)
        cx, cy = w/2, min(h*.42, 75 + ring_height*.52)
        rad = min((w - 34)/2, ring_height/2)
        p.setPen(QPen(QColor(118, 68, 79, 138), 1))
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.setPen(QPen(QColor(194, 107, 98, 90), .7))
        p.drawEllipse(QPointF(cx, cy), rad*.79, rad*.79)
        p.setPen(QPen(QColor(152, 71, 90, 75), .65))
        p.drawLine(QPointF(cx, cy-rad), QPointF(cx,cy+rad))
        p.drawLine(QPointF(cx-rad,cy), QPointF(cx+rad,cy))
        for a in (0, 90, 180, 270):
            theta=math.radians(a)
            x, y = cx+rad*math.cos(theta), cy+rad*math.sin(theta)
            p.setPen(QPen(QColor("#E0A971"), 1))
            p.drawLine(QPointF(x-7,y),QPointF(x+7,y))
            p.drawLine(QPointF(x,y-7),QPointF(x,y+7))

        # Sakura branches and subdued five-petal blossoms: decoration, not controls.
        p.setPen(QPen(QColor(131, 56, 74, 165), 1.15))
        for seed in range(3):
            y_base = h * (.55 + seed*.095)
            path = QPainterPath(QPointF(w-17, y_base+54))
            path.cubicTo(w-38, y_base+6, w-77, y_base+17, w-105, y_base-13)
            p.drawPath(path)
            for a, b in ((w-46,y_base+28),(w-70,y_base+15),(w-94,y_base-7)):
                self._blossom(p,a,b,4.7,78)
        p.end()
