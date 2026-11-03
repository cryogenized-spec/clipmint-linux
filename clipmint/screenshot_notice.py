"""Small actionable in-app capture notice.

Native system-tray notification click behavior varies across Cinnamon/Qt;
this on-window action is always a regular accessible Qt button.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class ScreenshotNotice(QFrame):
    def __init__(self, parent, on_edit, on_close):
        super().__init__(parent)
        self.setObjectName("screenshotNotice")
        self.setFixedWidth(374)
        self.setStyleSheet("""
            QFrame#screenshotNotice {
                background:#30202C; border:1px solid #D5A27E;
                border-radius:9px; }
            QFrame#screenshotNotice QLabel {
                color:#FFE7D6; border:0; background:transparent; }
            QPushButton {background:#E6CEC1;color:#281720;
                border:1px solid #F0DCCB;padding:8px 12px;border-radius:5px;}
            QPushButton:hover {background:#FFFFFF;}
            QPushButton#dismiss {background:transparent;color:#D6ABB3;
                border:0;padding:2px 6px;}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 12, 11)
        layout.setSpacing(6)
        top = QHBoxLayout()
        heading = QLabel("Screenshot captured")
        font = heading.font()
        font.setBold(True)
        font.setPointSize(12)
        heading.setFont(font)
        top.addWidget(heading, 1)
        close = QPushButton("×")
        close.setObjectName("dismiss")
        close.setAccessibleName("Dismiss screenshot notification")
        close.clicked.connect(on_close)
        top.addWidget(close)
        layout.addLayout(top)
        detail = QLabel("Your screenshot is saved. Open it to make changes.")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        action = QPushButton("Edit screenshot")
        action.setAccessibleName("Open captured screenshot in image editor")
        action.clicked.connect(on_edit)
        layout.addWidget(action)
        self.edit_button = action
        self.setAccessibleName("Screenshot captured — edit screenshot")
        self.hide()

    def position_inside_window(self):
        parent = self.parentWidget()
        if parent is not None:
            self.move(
                max(6, parent.width() - self.width() - 24),
                max(6, parent.height() - self.sizeHint().height() - 86),
            )

    def present(self):
        self.adjustSize()
        self.position_inside_window()
        self.show()
        self.raise_()
