"""Keyboard-first search popup for the running Qt clipboard manager.

It is shown near the cursor; it does not replace Kohaku's full archive UI.
Autocomplete is entirely local. The paste command targets only the explicit
X11 window captured immediately before the popup is shown.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import re
import shutil
import subprocess

from PySide6.QtCore import Qt, QEvent, QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication, QFrame, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget,
)

TERMINALS = ("gnome-terminal", "mate-terminal", "xfce4-terminal", "xterm",
             "tilix", "kitty", "konsole", "alacritty", "terminator", "wezterm")


def active_window() -> tuple[str | None, str]:
    if not shutil.which("xdotool"):
        return None, ""
    try:
        wid = subprocess.run(
            ["xdotool", "getactivewindow"], capture_output=True,
            text=True, timeout=1, check=True,
        ).stdout.strip()
        if not wid.isdecimal():
            return None, ""
        klass = subprocess.run(
            ["xdotool", "getwindowclassname", wid], capture_output=True,
            text=True, timeout=1, check=False,
        ).stdout.strip().lower()
        return wid, klass
    except (OSError, subprocess.SubprocessError):
        return None, ""


def paste_to_window(wid: str | None, klass: str, terminal_mode: str = "auto") -> bool:
    if not wid or not wid.isdecimal() or not shutil.which("xdotool"):
        return False
    terminal = (terminal_mode == "terminal") or (
        terminal_mode == "auto" and any(t in klass for t in TERMINALS)
    )
    key = "ctrl+shift+v" if terminal else "ctrl+v"
    try:
        result = subprocess.run(
            ["xdotool", "windowactivate", "--sync", wid, "key",
             "--clearmodifiers", key],
            capture_output=True, timeout=3, check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def fuzzy_score(needle: str, item: str) -> float:
    query = needle.casefold().strip()
    text = item.casefold()
    if not query:
        return 0
    if query in text:
        return 200 - min(text.index(query), 100)
    parts = text.split()
    token = max((SequenceMatcher(None, query, word).ratio()
                 for word in parts[:60]), default=0)
    whole = SequenceMatcher(None, query, text[:300]).ratio()
    return max(token, whole) * 100


class QuickPopup(QWidget):
    """No captured text is sent to a remote service."""
    def __init__(self, store, on_pick, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.store = store
        self.on_pick = on_pick
        self.target_window: str | None = None
        self.target_class = ""
        self.setObjectName("quickPopup")
        self.setFixedSize(555, 405)
        self.setStyleSheet("""
            QWidget#quickPopup {background:#211724;color:#F4E3DA;
                border:2px solid #B77480;border-radius:11px;}
            QLabel {color:#E6BBB3;background:transparent;border:0;
                font:12px Georgia;}
            QLineEdit {background:#342431;color:#FFF0E4;border:1px solid #BD7B83;
                border-radius:7px;padding:12px;font:13px "DejaVu Sans";}
            QListWidget {background:#221823;color:#EEE0D8;border:0;
                font:12px "DejaVu Sans";}
            QListWidget::item {padding:9px 8px;border-bottom:1px solid #48303F;}
            QListWidget::item:selected {background:#6F3448;color:#FFF2EC;}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 13, 15, 11)
        layout.setSpacing(9)
        layout.addWidget(QLabel("Kohaku  琥珀   /   QUICK ARCHIVE"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search saved clips…")
        self.search.textChanged.connect(self.refresh)
        self.search.installEventFilter(self)
        layout.addWidget(self.search)
        self.items = QListWidget()
        self.items.itemDoubleClicked.connect(lambda _item: self.pick(False))
        self.items.installEventFilter(self)
        layout.addWidget(self.items, 1)
        layout.addWidget(QLabel(
            "↑ ↓ select     Enter paste     Ctrl+Shift+Enter plain text     Esc close"))
        self.setAccessibleName("Quick clipboard history")

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.hide()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.items.count():
                    mods = event.modifiers()
                    plain = bool(
                        (mods & Qt.KeyboardModifier.ControlModifier)
                        and (mods & Qt.KeyboardModifier.ShiftModifier)
                    )
                    self.pick(plain)
                return True
            if watched == self.search and key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                row = self.items.currentRow()
                self.items.setCurrentRow(max(0, min(
                    self.items.count()-1, row + (-1 if key == Qt.Key.Key_Up else 1)
                )))
                return True
        return super().eventFilter(watched, event)

    def refresh(self, *_args):
        text = self.search.text()
        available = []
        for bin_name in self.store.bins():
            # Merge full-body FTS hits with the original fuzzy preview search.
            # Typo-tolerant search must keep working when FTS finds no terms.
            indexed = self.store.search(
                text, bin_name, sort="Best match"
            ) if text else []
            seen = set()
            for clip in indexed:
                seen.add(clip.id)
                score = max(70, fuzzy_score(text, clip.preview))
                available.append((score + (5 if clip.pinned else 0)
                                  + (4 if clip.favorite else 0), clip))
            for clip in self.store.search("", bin_name):
                if clip.id in seen:
                    continue
                score = fuzzy_score(text, clip.preview)
                if text and score < 45:
                    continue
                available.append((score + (5 if clip.pinned else 0)
                                  + (4 if clip.favorite else 0), clip))
        available.sort(key=lambda x: (-x[0], -x[1].id))
        self.items.clear()
        for _score, clip in available[:65]:
            prefix = "📌 " if clip.pinned else ""
            label = f"{prefix}{clip.preview[:110]}    · {clip.bin}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, clip.id)
            item.setToolTip(clip.preview)
            self.items.addItem(item)
        if self.items.count():
            self.items.setCurrentRow(0)

    def pick(self, plain: bool):
        item = self.items.currentItem()
        if item is None:
            return
        ident = item.data(Qt.ItemDataRole.UserRole)
        target, klass = self.target_window, self.target_class
        self.hide()
        self.on_pick(ident, plain, target, klass)

    def toggle(self):
        if self.isVisible():
            self.hide()
            return
        self.target_window, self.target_class = active_window()
        if "clipmint" in self.target_class:
            self.target_window = None  # Avoid pasting into our own app.
        self.search.clear()
        self.refresh()
        cursor = QCursor.pos()
        screen = QApplication.screenAt(cursor) or QApplication.primaryScreen()
        if screen is not None:
            bounds = screen.availableGeometry()
            x = max(bounds.left(), min(cursor.x(), bounds.right()-self.width()))
            y = max(bounds.top(), min(cursor.y(), bounds.bottom()-self.height()))
            self.move(QPoint(x, y))
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()
