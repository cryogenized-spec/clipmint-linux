"""Dedicated, always-visible recording controller and keyboard-friendly save dialog."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from time import monotonic

from PySide6.QtCore import Qt, QTimer, QRect, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QWidget, QApplication,
)


def clock_display(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02}:{total // 60 % 60:02}:{total % 60:02}"


def size_display(byte_count: float) -> str:
    return f"{byte_count / 1024 / 1024:.1f} MB"


class RecorderWindow(QWidget):
    """This window replaces the main window throughout a recording session."""

    start_requested = Signal(str, str)
    stop_requested = Signal()
    cancelled = Signal()

    def __init__(self, region: QRect, file_format: str = "MP4", parent=None):
        super().__init__(parent)
        self.region = region
        self.started_at: float | None = None
        self.estimated_bytes_per_second = 450_000
        self.output: Path | None = None
        self._busy = False
        self.setWindowTitle("ClipMint · Screen Recorder")
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(660)
        self.setStyleSheet("""
            QWidget {background:#101c30;color:#eaf5ff;font-size:13px;}
            QPushButton {background:#162b48;color:#e8f5ff;border:1px solid #3971a2;
                padding:12px 16px;border-radius:10px;font-weight:600;}
            QPushButton:hover {border:1px solid #41e4cc;background:#243d5c;}
            QPushButton#toggle {background:#145e59;border:2px solid #36dfc0;font-size:17px;}
            QPushButton#toggle:disabled {background:#343c4e;color:#a3b1c0;}
            QComboBox {background:#152640;border:1px solid #537494;
                padding:8px;border-radius:8px;min-width:98px;}
            QLabel#clock {font-size:25px;font-weight:700;}
            QLabel#hint {color:#9fb9cc;}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(10)
        top = QHBoxLayout()
        brand = QLabel("◉  ClipMint  /  Recorder")
        brand.setStyleSheet("font-size:17px;font-weight:700;color:#50e6ca;")
        top.addWidget(brand)
        top.addStretch()
        self.state = QLabel("●  Ready")
        top.addWidget(self.state)
        root.addLayout(top)
        info = QHBoxLayout()
        self.button = QPushButton("●  Start recording")
        self.button.setObjectName("toggle")
        self.button.clicked.connect(self.toggle)
        info.addWidget(self.button)
        centre = QVBoxLayout()
        self.timer_label = QLabel("00:00:00")
        self.timer_label.setObjectName("clock")
        centre.addWidget(self.timer_label)
        self.size_label = QLabel("≈ 0.0 MB estimated")
        self.size_label.setObjectName("hint")
        centre.addWidget(self.size_label)
        info.addLayout(centre)
        info.addStretch()
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP4", "GIF"])
        self.format_combo.setCurrentText(file_format)
        info.addWidget(self.format_combo)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["High", "Medium", "Low"])
        info.addWidget(self.quality_combo)
        root.addLayout(info)
        self.region_label = QLabel(f"Capture area: {region.width()} × {region.height()} px")
        self.region_label.setObjectName("hint")
        root.addWidget(self.region_label)
        self.ticker = QTimer(self)
        self.ticker.setInterval(250)
        self.ticker.timeout.connect(self.update_time)

    def place_outside(self):
        """Prefer a position outside the selected region, to avoid recording controls."""
        screen = QApplication.primaryScreen()
        if screen is None:
            self.show()
            return
        desktop = screen.availableGeometry()
        w, h = max(self.minimumWidth(), self.sizeHint().width()), self.sizeHint().height()
        x = max(desktop.left(), min(self.region.center().x() - w // 2, desktop.right() - w + 1))
        below = self.region.bottom() + 12
        above = self.region.top() - h - 12
        if below + h <= desktop.bottom():
            y = below
        elif above >= desktop.top():
            y = above
        else:
            # Full screen / large captures have no spare space. Controls may appear in output.
            y = max(desktop.top(), desktop.bottom() - h + 1)
            self.region_label.setText(self.region_label.text() + "  ·  Controls may be captured")
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle(self):
        if self._busy:
            return
        if self.started_at is None:
            self._busy = True
            self.start_requested.emit(self.quality_combo.currentText(), self.format_combo.currentText())
        else:
            self._busy = True
            self.button.setEnabled(False)
            self.state.setText("●  Finalizing…")
            self.stop_requested.emit()

    def recording_started(self, output: Path, estimate_per_second: float):
        self.output = output
        self.started_at = monotonic()
        self.estimated_bytes_per_second = estimate_per_second
        self._busy = False
        self.state.setText("●  Recording")
        self.state.setStyleSheet("color:#ff788b;font-weight:600;")
        self.button.setText("■  Stop recording")
        self.format_combo.setEnabled(False)
        self.quality_combo.setEnabled(False)
        self.ticker.start()
        self.update_time()

    def start_failed(self):
        self._busy = False
        self.button.setEnabled(True)
        self.state.setText("●  Ready")

    def update_time(self):
        if self.started_at is None:
            return
        elapsed = monotonic() - self.started_at
        self.timer_label.setText(clock_display(elapsed))
        self.size_label.setText(f"≈ {size_display(elapsed * self.estimated_bytes_per_second)} estimated")

    def recording_finished(self):
        self.ticker.stop()
        self.hide()

    def closeEvent(self, event):
        if self.started_at is not None:
            event.ignore()
            self.toggle()
        else:
            self.cancelled.emit()
            event.accept()


class SaveClipDialog(QDialog):
    """Yes is the default; Enter accepts, left/right switches Yes and No."""

    def __init__(self, path: Path, duration: str, quality: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ClipMint · Save recording?")
        self.setModal(True)
        self.setMinimumWidth(410)
        self.setStyleSheet("""
            QDialog {background:#111e33;color:#eaf5ff;}
            QLabel {color:#eaf5ff;font-size:14px;}
            QPushButton {padding:13px 24px;border-radius:10px;font-weight:700;
                border:1px solid #7893b0;background:#273951;color:#f2f7ff;}
            QPushButton:focus {border:2px solid #55efd1;}
            QPushButton#yes {background:#115951;border:2px solid #4aebc6;}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 22)
        title = QLabel("Save this clip?")
        title.setStyleSheet("font-size:24px;font-weight:700;")
        root.addWidget(title)
        size = size_display(path.stat().st_size) if path.exists() else "Unknown size"
        root.addWidget(QLabel(f"{duration}   •   {size}   •   {quality}   •   {path.suffix[1:].upper()}"))
        root.addWidget(QLabel("This recording is not saved until you confirm."))
        buttons = QHBoxLayout()
        self.yes_button = QPushButton("✓  Yes (Save)")
        self.yes_button.setObjectName("yes")
        self.yes_button.setDefault(True)
        self.yes_button.clicked.connect(self.accept)
        self.no_button = QPushButton("No (Discard)")
        self.no_button.clicked.connect(self.reject)
        buttons.addWidget(self.yes_button)
        buttons.addWidget(self.no_button)
        root.addLayout(buttons)
        hint = QLabel("Enter = confirm selected option   •   ← / → = switch")
        hint.setStyleSheet("font-size:11px;color:#a5bacb;")
        root.addWidget(hint)
        self.yes_button.setFocus()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            other = self.no_button if self.yes_button.hasFocus() else self.yes_button
            other.setFocus()
            self.yes_button.setDefault(other is self.yes_button)
            self.no_button.setDefault(other is self.no_button)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.no_button.hasFocus():
                self.reject()
            else:
                self.accept()
            return
        super().keyPressEvent(event)
