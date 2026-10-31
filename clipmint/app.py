"""ClipMint desktop application — mouse-driven clipboard and screen capture."""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys

from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPushButton, QStyle, QSystemTrayIcon,
    QVBoxLayout, QWidget,
)

from .capture import AreaSelector, RegionRecorder, recordings_dir, screenshots_dir, stamped_filename
from .store import ClipStore


class ClipMintWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClipMint · Clipboard & Capture")
        self.resize(820, 570)
        self.store = ClipStore()
        self.recorder = RegionRecorder()
        self.monitoring = True
        self.selector: AreaSelector | None = None

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        heading = QLabel("ClipMint")
        heading.setStyleSheet("font-size: 26px; font-weight: 700;")
        layout.addWidget(heading)
        label = QLabel("Copy text or images normally. Right-click any saved item to copy, pin, or delete it.")
        label.setWordWrap(True)
        layout.addWidget(label)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search your clipboard history…")
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)

        self.history = QListWidget()
        self.history.setAlternatingRowColors(True)
        self.history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history.customContextMenuRequested.connect(self.context_menu)
        self.history.itemDoubleClicked.connect(self.copy_clip)
        layout.addWidget(self.history, 1)

        row = QHBoxLayout()
        self.screenshot_button = QPushButton("Screenshot area")
        self.screenshot_button.clicked.connect(self.choose_screenshot)
        row.addWidget(self.screenshot_button)
        self.record_button = QPushButton("Record area")
        self.record_button.clicked.connect(self.choose_recording)
        row.addWidget(self.record_button)
        self.stop_button = QPushButton("Stop recording")
        self.stop_button.clicked.connect(self.stop_recording)
        row.addWidget(self.stop_button)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.pause_button = QPushButton("Pause monitoring")
        self.pause_button.clicked.connect(self.toggle_monitoring)
        row.addWidget(self.pause_button)
        folder_button = QPushButton("Open recordings folder")
        folder_button.clicked.connect(lambda: self.open_folder(recordings_dir()))
        row.addWidget(folder_button)
        layout.addLayout(row)

        self.setCentralWidget(panel)
        self.setStatusTip("ClipMint operates locally. No shortcuts required.")
        self.statusBar().showMessage("Ready — select an item, or choose Screenshot / Record area")
        self.configure_tray()
        QApplication.clipboard().dataChanged.connect(self.clipboard_changed)
        self.poller = QTimer(self)
        self.poller.timeout.connect(self.poll_recording)
        self.poller.start(400)
        self.refresh()
        self.update_buttons()
        QTimer.singleShot(400, self.clipboard_changed)

    def configure_tray(self):
        self.tray = None
        self.tray_stop = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), self
        )
        menu = QMenu(self)
        menu.addAction("Show ClipMint").triggered.connect(self.show_window)
        menu.addSeparator()
        menu.addAction("Screenshot area").triggered.connect(self.choose_screenshot)
        menu.addAction("Record area").triggered.connect(self.choose_recording)
        self.tray_stop = menu.addAction("Stop recording")
        self.tray_stop.triggered.connect(self.stop_recording)
        menu.addSeparator()
        menu.addAction("Quit ClipMint").triggered.connect(self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def inform(self, title: str, message: str):
        self.statusBar().showMessage(f"{title}: {message}", 7000)
        if self.tray is not None:
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def error(self, title: str, message: str):
        self.statusBar().showMessage(message, 10000)
        QMessageBox.warning(self, title, message)

    def clipboard_changed(self):
        if not self.monitoring:
            return
        clipboard = QApplication.clipboard()
        data = clipboard.mimeData()
        if data is None:
            return
        if data.hasImage():
            image = clipboard.image()
            if image.isNull():
                return
            out = QByteArray()
            buffer = QBuffer(out)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            saved = image.save(buffer, "PNG")
            buffer.close()
            if saved and len(out) < 16 * 1024 * 1024:
                self.store.add("image", bytes(out), f"Image {image.width()} × {image.height()}")
        elif data.hasText():
            text = data.text()
            if text.strip():
                payload = text.encode("utf-8")
                if len(payload) <= 2 * 1024 * 1024:
                    self.store.add("text", payload, " ".join(text.split())[:550])
        self.refresh()

    def refresh(self, *_args):
        previous = self.selected_id()
        self.history.clear()
        for clip in self.store.search(self.search.text()):
            prefix = "📌 " if clip.pinned else ("🖼 " if clip.kind == "image" else "📋 ")
            item = QListWidgetItem(prefix + clip.preview)
            item.setData(Qt.ItemDataRole.UserRole, clip.id)
            item.setToolTip(f"{clip.kind} · {clip.created_at}")
            self.history.addItem(item)
            if clip.id == previous:
                self.history.setCurrentItem(item)

    def selected_id(self):
        item = self.history.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def context_menu(self, position):
        item = self.history.itemAt(position)
        if item is None:
            return
        self.history.setCurrentItem(item)
        clip_id = item.data(Qt.ItemDataRole.UserRole)
        pinned = self.store.pinned(clip_id)
        menu = QMenu(self)
        copy = menu.addAction("Copy")
        pin = menu.addAction("Unpin snippet" if pinned else "Pin as snippet")
        delete = menu.addAction("Delete")
        choice = menu.exec(self.history.viewport().mapToGlobal(position))
        if choice == copy:
            self.copy_clip(item)
        elif choice == pin:
            self.store.pin(clip_id, not pinned)
            self.refresh()
        elif choice == delete:
            self.store.delete(clip_id)
            self.refresh()

    def copy_clip(self, item):
        value = self.store.get(item.data(Qt.ItemDataRole.UserRole))
        if value is None:
            return
        kind, contents = value
        clipboard = QApplication.clipboard()
        if kind == "text":
            clipboard.setText(contents.decode("utf-8", errors="replace"))
        else:
            image = QImage.fromData(contents, "PNG")
            if image.isNull():
                self.error("Clipboard", "This image cannot be decoded")
                return
            clipboard.setImage(image)
        self.inform("Copied", "Selected snippet copied to the system clipboard")

    def toggle_monitoring(self):
        self.monitoring = not self.monitoring
        self.pause_button.setText("Pause monitoring" if self.monitoring else "Resume monitoring")
        self.inform("Clipboard monitoring", "Enabled" if self.monitoring else "Paused")

    def select_area(self, purpose: str):
        if self.selector is not None:
            return
        if purpose == "video" and self.recorder.process is not None:
            self.inform("Recording", "Finish the current recording first")
            return
        # Hide this window so it is not captured in the desktop snapshot.
        self.hide()
        QTimer.singleShot(180, lambda: self.begin_selection(purpose))

    def begin_selection(self, purpose):
        try:
            self.selector = AreaSelector()
        except Exception as exc:
            self.show_window()
            self.error("Screen capture", str(exc))
            return
        self.selector.cancelled.connect(self.selection_cancelled)
        if purpose == "image":
            self.selector.selected.connect(self.save_screenshot)
        else:
            self.selector.selected.connect(self.start_video)

    def clear_selection(self):
        self.selector = None

    def selection_cancelled(self):
        QTimer.singleShot(0, self.clear_selection)
        self.show_window()

    def choose_screenshot(self):
        self.select_area("image")

    def save_screenshot(self, _rect, pixmap):
        QTimer.singleShot(0, self.clear_selection)
        path = screenshots_dir() / stamped_filename("screenshot", "png")
        if not pixmap.save(str(path), "PNG"):
            self.show_window()
            self.error("Screenshot", "Could not save PNG")
            return
        QApplication.clipboard().setImage(pixmap.toImage())
        self.show_window()
        self.inform("Screenshot saved", str(path))

    def choose_recording(self):
        self.select_area("video")

    def start_video(self, rect, _pixmap):
        QTimer.singleShot(0, self.clear_selection)
        # Let Qt remove the area-selection overlay before FFmpeg starts.
        QTimer.singleShot(300, lambda: self.launch_recorder(rect))

    def launch_recorder(self, rect):
        try:
            path = self.recorder.start(rect)
        except Exception as exc:
            self.show_window()
            self.error("Recording", str(exc))
            return
        # Keep the Stop button accessible even if Cinnamon has no tray.
        self.show_window()
        self.update_buttons()
        self.inform("Recording started", f"Click Stop recording to save: {path.name}")

    def stop_recording(self):
        if self.recorder.stop():
            self.statusBar().showMessage("Finalizing MP4…")
        elif not self.recorder.active:
            self.inform("Recording", "No active recording")
        self.update_buttons()

    def poll_recording(self):
        result = self.recorder.finished()
        if result is None:
            return
        status, path = result
        if status == 0 and path and path.exists() and path.stat().st_size:
            self.inform("Recording saved", str(path))
        else:
            self.error("Recording error", "FFmpeg failed; see the .ffmpeg.log file beside the recording")
        self.update_buttons()

    def update_buttons(self):
        active = self.recorder.active
        self.record_button.setEnabled(not active)
        self.stop_button.setEnabled(active and not self.recorder.stopping)
        if self.tray_stop is not None:
            self.tray_stop.setEnabled(active and not self.recorder.stopping)

    def open_folder(self, folder: Path):
        try:
            subprocess.Popen(["xdg-open", str(folder)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError as exc:
            self.error("Open folder", str(exc))

    def closeEvent(self, event):
        if self.tray is not None:
            self.hide()
            event.ignore()
        elif self.recorder.active:
            self.error("Recording active", "Stop recording before closing ClipMint")
            event.ignore()
        else:
            self.store.close()
            event.accept()

    def quit_app(self):
        if self.recorder.process is not None:
            self.error("Recording active", "Finish recording before quitting")
            return
        self.store.close()
        if self.tray is not None:
            self.tray.hide()
        QApplication.quit()


def main():
    if sys.platform != "linux":
        raise SystemExit("ClipMint currently supports Linux only")
    app = QApplication(sys.argv)
    app.setApplicationName("ClipMint")
    if os.environ.get("XDG_SESSION_TYPE", "x11").lower() != "x11":
        QMessageBox.warning(None, "X11 required",
                            "ClipMint v0.1 requires an X11 session (such as Cinnamon X11).")
        raise SystemExit(1)
    window = ClipMintWindow()
    window.show()
    raise SystemExit(app.exec())
