"""Non-intrusive screenshot actions, independent of the main ClipMint window.

The capture notification is a small top-level tool window. It must not reveal
ClipMint, activate itself, or steal keyboard focus from Firefox / another app.
"""
from __future__ import annotations

import shutil
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)


def play_capture_sound() -> bool:
    """Try the desktop's standard camera-shutter event, without new dependencies.

    Sound is best-effort. Missing sound-theme support must never interrupt a
    saved screenshot or clipboard paste, and this never starts a shell.
    """
    player = shutil.which("canberra-gtk-play")
    if not player:
        return False
    try:
        subprocess.Popen(
            [player, "-i", "camera-shutter", "-d", "ClipMint"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return False
    return True


class ScreenshotNotice(QFrame):
    """Mouse-only two-action popup in the desktop's lower-right work area."""

    def __init__(self, parent, on_edit, on_close, on_ocr=None):
        # Deliberately parentless at the Qt window level: hiding the main
        # window must not hide this independent, nonactivating tool window.
        # The owner retains the Python reference and supplies the callbacks.
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setObjectName("screenshotNotice")
        self.setFixedWidth(340)
        self.setStyleSheet("""
            QFrame#screenshotNotice {
                background:#201820; border:1px solid #9E4657;
                border-radius:9px;
            }
            QFrame#screenshotNotice QLabel {
                color:#F2E8E9; border:0; background:transparent;
            }
            QFrame#screenshotNotice QLabel#noticeMeta {
                color:#BFAEB4; font-size:12px;
            }
            QFrame#screenshotNotice QPushButton#noticeAction {
                background:#30222D; color:#F8EBED;
                border:1px solid #67404B; border-radius:5px;
                text-align:left; padding:12px 13px; font-weight:600;
            }
            QFrame#screenshotNotice QPushButton#noticeAction:hover {
                background:#482936; border-color:#B35B70;
            }
            QFrame#screenshotNotice QPushButton#dismiss {
                background:transparent; color:#BFAEB4; border:0;
                padding:1px 6px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(7)
        top = QHBoxLayout()
        heading = QLabel("Screenshot copied")
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        top.addWidget(heading, 1)
        dismiss = QPushButton("×")
        dismiss.setObjectName("dismiss")
        dismiss.setAccessibleName("Dismiss screenshot actions")
        dismiss.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        dismiss.clicked.connect(on_close)
        top.addWidget(dismiss)
        layout.addLayout(top)
        detail = QLabel("Saved as PNG · Ctrl+V to paste")
        detail.setObjectName("noticeMeta")
        layout.addWidget(detail)

        self.edit_button = QPushButton("Edit screenshot")
        self.edit_button.setObjectName("noticeAction")
        self.edit_button.setAccessibleName("Open captured screenshot in image editor")
        self.edit_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.edit_button.clicked.connect(on_edit)
        layout.addWidget(self.edit_button)
        self.ocr_button = None
        if on_ocr is not None:
            self.ocr_button = QPushButton("Extract text · OCR")
            self.ocr_button.setObjectName("noticeAction")
            self.ocr_button.setAccessibleName(
                "Extract text from the screenshot and copy recognized text"
            )
            self.ocr_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.ocr_button.clicked.connect(on_ocr)
            layout.addWidget(self.ocr_button)
        self.setAccessibleName("Screenshot copied · edit or extract text")
        self.hide()

    def position_near_desktop_corner(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        work = screen.availableGeometry()
        self.move(
            max(work.left() + 12, work.right() - self.width() - 18),
            max(work.top() + 12, work.bottom() - self.height() - 18),
        )

    def present(self):
        self.adjustSize()
        self.position_near_desktop_corner()
        self.show()
        # Raising a WindowDoesNotAcceptFocus tool does not activate it.
        self.raise_()
