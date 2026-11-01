"""ClipMint: self-contained, mouse-first clipboard bins and screen capture for Cinnamon X11."""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys

from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QPushButton, QStyle, QSystemTrayIcon,
    QTabBar, QToolButton, QVBoxLayout, QWidget, QStackedWidget,
)

from .capture import AreaSelector, RegionRecorder, recordings_dir, screenshots_dir, stamped_filename
from .recording_ui import RecorderWindow, SaveClipDialog
from .store import ClipStore, classify, looks_sensitive


THEME = """
QMainWindow, QWidget#appRoot {background:#0e1627;color:#e5f2ff;}
QLabel {color:#e5f2ff;}
QLabel#brand {color:#50e4ca;font-size:25px;font-weight:750;}
QLabel#muted {color:#9bb3cd;}
QLineEdit,QComboBox {background:#14263f;color:#eef8ff;border:1px solid #345572;
    padding:10px;border-radius:9px;selection-background-color:#31688b;}
QLineEdit:focus,QComboBox:focus {border:1px solid #48e5c4;}
QListWidget {background:#111f33;color:#ebf4ff;border:1px solid #36516c;
    border-radius:12px;padding:8px;outline:none;}
QListWidget::item {padding:12px 8px;border-bottom:1px solid #253b51;}
QListWidget::item:selected {background:#23456b;border-radius:8px;}
QPushButton,QToolButton {background:#1c304c;color:#eaf6ff;border:1px solid #42678f;
    border-radius:9px;padding:11px 14px;font-weight:600;}
QPushButton:hover,QToolButton:hover {background:#294666;border:1px solid #5debd4;}
QPushButton:checked {background:#175c72;border:1px solid #4fe3c9;}
QPushButton#record {background:#114e48;border:2px solid #32d9bf;}
QPushButton#screenshot {background:#392454;border:2px solid #a26fe1;}
QTabBar::tab {background:#1c2d4a;color:#d9ecff;border:1px solid #3f597b;
    padding:13px 25px;border-radius:9px;margin-right:7px;}
QTabBar::tab:selected {background:#185c73;border:2px solid #45ebce;}
QFrame#sidebar {background:#101b2d;border:1px solid #273b53;border-radius:12px;}
QFrame#preview {background:#121e31;border:1px solid #2e4c6b;border-radius:12px;}
QStatusBar {background:#0b1524;color:#9bb3cd;}
"""


class ClipMintWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClipMint · Clipboard & Capture")
        self.resize(1080, 700)
        self.setMinimumSize(850, 500)
        self.setStyleSheet(THEME)
        self.store = ClipStore()
        self.recorder = RegionRecorder()
        self.monitoring = True
        self.selector: AreaSelector | None = None
        self.recorder_window: RecorderWindow | None = None
        self.capture_rect = None
        self.capture_format = "MP4"
        self._privacy_skipped = 0
        self._closing = False

        shell = QWidget()
        shell.setObjectName("appRoot")
        root = QVBoxLayout(shell)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(14)
        header = QHBoxLayout()
        heading = QLabel("◈  ClipMint  ve-02")
        heading.setObjectName("brand")
        header.addWidget(heading)
        header.addStretch()
        title = QLabel("Local clipboard hub  •  Cinnamon X11")
        title.setObjectName("muted")
        header.addWidget(title)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        nav_layout = QVBoxLayout(sidebar)
        nav_layout.setContentsMargins(12, 14, 12, 14)
        nav_layout.setSpacing(9)
        self.nav_buttons: dict[str, QPushButton] = {}
        for index, name in enumerate(("Clipboard", "Screenshots", "Recordings",
                                       "Secrets & Variables", "Autosort", "Settings")):
            b = QPushButton(name)
            b.setCheckable(True)
            b.clicked.connect(lambda _checked=False, i=index: self.open_section(i))
            self.nav_buttons[name] = b
            nav_layout.addWidget(b)
        nav_layout.addStretch()
        body.addWidget(sidebar)
        root.addLayout(body, 1)

        self.build_clipboard_page()
        self.build_library_page("Screenshots")
        self.build_library_page("Recordings")
        self.build_info_page("Secrets & Variables", (
            "Private by default\n\n"
            "ClipMint does not offer a secure password vault. Obvious password/token "
            "assignments are skipped by the clipboard monitor, but automatic detection "
            "cannot find every secret. Pause monitoring when handling credentials.\n\n"
            "Saved clipboard history is not encrypted. Do not store passwords or API keys "
            "in an accumulation bin."
        ))
        self.build_info_page("Autosort", (
            "Automatic content classification\n\n"
            "Use the Type filter in the Clipboard view to show URLs, phone numbers, "
            "images or text. These built-in categories do not move or erase clips.\n\n"
            "Custom rules, templates and variable extraction are planned, "
            "but are not yet enabled in this preview."
        ))
        self.build_settings_page()

        footer = QHBoxLayout()
        self.record_button = QPushButton("●  Start Recording  MP4 / GIF")
        self.record_button.setObjectName("record")
        self.record_button.clicked.connect(lambda: self.choose_recording("MP4"))
        footer.addWidget(self.record_button, 2)
        self.record_menu = QToolButton()
        self.record_menu.setText("▾")
        self.record_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        formats = QMenu(self.record_menu)
        formats.addAction("Record MP4").triggered.connect(lambda: self.choose_recording("MP4"))
        formats.addAction("Record GIF").triggered.connect(lambda: self.choose_recording("GIF"))
        self.record_menu.setMenu(formats)
        footer.addWidget(self.record_menu)
        self.screenshot_button = QPushButton("▣  Screenshot")
        self.screenshot_button.setObjectName("screenshot")
        self.screenshot_button.clicked.connect(self.screenshot_full)
        footer.addWidget(self.screenshot_button, 2)
        self.screenshot_menu = QToolButton()
        self.screenshot_menu.setText("▾")
        self.screenshot_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        captures = QMenu(self.screenshot_menu)
        captures.addAction("Full screen (default)").triggered.connect(self.screenshot_full)
        captures.addAction("Select area").triggered.connect(self.choose_screenshot)
        self.screenshot_menu.setMenu(captures)
        footer.addWidget(self.screenshot_menu)
        root.addLayout(footer)

        self.setCentralWidget(shell)
        self.statusBar().showMessage("Ready · Left-click a clip, right-click for Copy / Pin / Move / Delete")
        self.configure_tray()
        QApplication.clipboard().dataChanged.connect(self.clipboard_changed)
        self.poller = QTimer(self)
        self.poller.timeout.connect(self.poll_recording)
        self.poller.start(300)
        self.open_section(0)
        QTimer.singleShot(400, self.clipboard_changed)

    def build_clipboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        bins = QHBoxLayout()
        self.tabs = QTabBar()
        self.tabs.setExpanding(True)
        self.tabs.setDrawBase(False)
        for name in self.store.bins():
            self.tabs.addTab(name)
        self.tabs.currentChanged.connect(self.refresh)
        bins.addWidget(self.tabs, 1)
        add_bin = QPushButton("+")
        add_bin.setToolTip("Add a new accumulation bin")
        add_bin.clicked.connect(self.new_bin)
        bins.addWidget(add_bin)
        layout.addLayout(bins)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search clips in this bin…")
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)
        sorts = QHBoxLayout()
        sorts.addWidget(QLabel("View:"))
        self.category = QComboBox()
        self.category.addItems(["All", "Text", "URLs", "Phone numbers", "Images"])
        self.category.currentIndexChanged.connect(self.refresh)
        sorts.addWidget(self.category)
        sorts.addWidget(QLabel("Sort:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Latest first", "Oldest first", "A–Z", "Z–A", "Numbered list"])
        self.sort_combo.currentIndexChanged.connect(self.refresh)
        sorts.addWidget(self.sort_combo)
        sorts.addStretch()
        layout.addLayout(sorts)
        self.count_label = QLabel("Clipboard")
        self.count_label.setStyleSheet("font-size:15px;font-weight:700;")
        layout.addWidget(self.count_label)
        middle = QHBoxLayout()
        middle.setSpacing(12)
        self.history = QListWidget()
        self.history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history.customContextMenuRequested.connect(self.context_menu)
        self.history.itemDoubleClicked.connect(self.copy_clip)
        self.history.currentItemChanged.connect(self.preview_clip)
        middle.addWidget(self.history, 4)
        preview_frame = QFrame()
        preview_frame.setObjectName("preview")
        preview_frame.setMinimumWidth(185)
        preview_frame.setMaximumWidth(290)
        right = QVBoxLayout(preview_frame)
        right.addWidget(QLabel("PREVIEW"))
        self.preview_label = QLabel("Select an item to preview")
        self.preview_label.setWordWrap(True)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right.addWidget(self.preview_label, 1)
        copy = QPushButton("Copy selected")
        copy.clicked.connect(self.copy_selected)
        right.addWidget(copy)
        middle.addWidget(preview_frame, 2)
        layout.addLayout(middle, 1)
        self.pages.addWidget(page)

    def build_library_page(self, kind: str):
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel(f"{kind} · saved locally")
        heading.setStyleSheet("font-size:20px;font-weight:700;")
        layout.addWidget(heading)
        listing = QListWidget()
        listing.itemDoubleClicked.connect(self.open_saved_file)
        layout.addWidget(listing, 1)
        path = screenshots_dir() if kind == "Screenshots" else recordings_dir()
        bottom = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(lambda: self.refresh_library(kind))
        bottom.addWidget(refresh)
        folder = QPushButton("Open folder")
        folder.clicked.connect(lambda: self.open_folder(path))
        bottom.addWidget(folder)
        layout.addLayout(bottom)
        if not hasattr(self, "libraries"):
            self.libraries = {}
        self.libraries[kind] = listing
        self.pages.addWidget(page)

    def build_info_page(self, title: str, description: str):
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel(title)
        heading.setStyleSheet("font-size:22px;font-weight:700;color:#58e6cc;")
        layout.addWidget(heading)
        label = QLabel(description)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop)
        label.setStyleSheet("font-size:14px;")
        layout.addWidget(label)
        layout.addStretch()
        self.pages.addWidget(page)

    def build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Settings · local-only"))
        self.pause_button = QPushButton("Pause monitoring")
        self.pause_button.clicked.connect(self.toggle_monitoring)
        layout.addWidget(self.pause_button)
        open_files = QPushButton("Open recordings folder")
        open_files.clicked.connect(lambda: self.open_folder(recordings_dir()))
        layout.addWidget(open_files)
        layout.addWidget(QLabel("No network access or global keyboard shortcuts are required."))
        layout.addWidget(QLabel("History is stored locally and is not encrypted."))
        layout.addStretch()
        self.pages.addWidget(page)

    def active_bin(self) -> str:
        return self.tabs.tabText(self.tabs.currentIndex()) if self.tabs.currentIndex() >= 0 else "Work"

    def new_bin(self):
        name, ok = QInputDialog.getText(self, "New accumulation bin", "Bin name:")
        if not ok or not name.strip():
            return
        try:
            self.store.add_bin(name.strip())
        except (ValueError, OSError, Exception) as exc:
            self.error("Bin", str(exc))
            return
        index = self.tabs.addTab(name.strip())
        self.tabs.setCurrentIndex(index)

    def open_section(self, index: int):
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons.values()):
            button.setChecked(index == i)
        if index == 1:
            self.refresh_library("Screenshots")
        elif index == 2:
            self.refresh_library("Recordings")
        elif index == 0:
            self.refresh()

    def refresh_library(self, kind: str):
        listing = self.libraries[kind]
        listing.clear()
        folder = screenshots_dir() if kind == "Screenshots" else recordings_dir()
        formats = (".png",) if kind == "Screenshots" else (".mp4", ".gif")
        for path in sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.suffix.lower() not in formats or path.name.startswith("."):
                continue
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            listing.addItem(item)

    def open_saved_file(self, item):
        target = Path(item.data(Qt.ItemDataRole.UserRole))
        if target.is_file():
            self.open_path(target)

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
        menu.addAction("Screenshot full screen").triggered.connect(self.screenshot_full)
        menu.addAction("Screenshot selected area").triggered.connect(self.choose_screenshot)
        menu.addAction("Record MP4").triggered.connect(lambda: self.choose_recording("MP4"))
        menu.addAction("Record GIF").triggered.connect(lambda: self.choose_recording("GIF"))
        self.tray_stop = menu.addAction("Stop recording")
        self.tray_stop.triggered.connect(self.stop_recording)
        menu.addSeparator()
        menu.addAction("Quit ClipMint").triggered.connect(self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger and self.recorder_window is None:
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
        QMessageBox.warning(self.recorder_window or self, title, message)

    def clipboard_changed(self):
        if not self.monitoring:
            return
        data = QApplication.clipboard().mimeData()
        if data is None:
            return
        active = self.active_bin()
        if data.hasImage():
            picture = QApplication.clipboard().image()
            if picture.isNull():
                return
            result = QByteArray()
            buffer = QBuffer(result)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            saved = picture.save(buffer, "PNG")
            buffer.close()
            if saved and len(result) < 16 * 1024 * 1024:
                self.store.add("image", bytes(result), f"Image {picture.width()} × {picture.height()}", active)
        elif data.hasText():
            text = data.text()
            if text.strip():
                if looks_sensitive(text):
                    self._privacy_skipped += 1
                    self.statusBar().showMessage("Potential credential excluded from history")
                    return
                payload = text.encode("utf-8")
                if len(payload) <= 2 * 1024 * 1024:
                    self.store.add("text", payload, " ".join(text.split())[:550], active)
        self.refresh()

    def refresh(self, *_args):
        previous = self.selected_id() if hasattr(self, "history") else None
        if not hasattr(self, "history"):
            return
        self.history.clear()
        bin_name = self.active_bin()
        category = self.category.currentText()
        sort = self.sort_combo.currentText()
        clips = self.store.search(self.search.text(), bin_name, sort, category)
        numbered = sort == "Numbered list"
        for i, clip in enumerate(clips):
            icon = "📌" if clip.pinned else ("🖼" if clip.kind == "image" else "📋")
            text = f"{i+1}.  {icon}  {clip.preview}" if numbered else f"{icon}  {clip.preview}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, clip.id)
            item.setToolTip(f"{classify(clip)} · {clip.created_at} · {clip.bin}")
            self.history.addItem(item)
            if clip.id == previous:
                self.history.setCurrentItem(item)
        self.count_label.setText(f"Clipboard ({bin_name})  ·  {len(clips)} shown / {self.store.count(bin_name)} total")
        if self.history.currentItem() is None:
            self.preview_label.setText("Select an item to preview")

    def preview_clip(self, current, _old):
        if current is None:
            self.preview_label.setText("Select an item to preview")
            return
        value = self.store.get(current.data(Qt.ItemDataRole.UserRole))
        if value is None:
            return
        kind, contents = value
        if kind == "text":
            self.preview_label.setText(contents.decode("utf-8", errors="replace")[:5000])
        else:
            image = QImage.fromData(contents, "PNG")
            self.preview_label.setText(f"Image · {image.width()} × {image.height()} pixels")

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
        pin = menu.addAction("Unpin" if pinned else "Pin")
        move_menu = menu.addMenu("Move to bin")
        moves = {}
        for name in self.store.bins():
            if name != self.active_bin():
                moves[move_menu.addAction(name)] = name
        delete = menu.addAction("Delete")
        choice = menu.exec(self.history.viewport().mapToGlobal(position))
        if choice == copy:
            self.copy_clip(item)
        elif choice == pin:
            self.store.pin(clip_id, not pinned)
            self.refresh()
        elif choice in moves:
            self.store.move(clip_id, moves[choice])
            self.refresh()
        elif choice == delete:
            self.store.delete(clip_id)
            self.refresh()

    def copy_selected(self):
        item = self.history.currentItem()
        if item is not None:
            self.copy_clip(item)

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
                self.error("Clipboard", "Image could not be decoded")
                return
            clipboard.setImage(image)
        self.inform("Copied", "Saved snippet copied to the system clipboard")

    def toggle_monitoring(self):
        self.monitoring = not self.monitoring
        self.pause_button.setText("Pause monitoring" if self.monitoring else "Resume monitoring")
        self.inform("Clipboard monitoring", "Enabled" if self.monitoring else "Paused")

    def select_area(self, purpose: str):
        if self.selector is not None or self.recorder_window is not None:
            return
        if purpose == "video" and self.recorder.process is not None:
            self.inform("Recording", "Finish the current recording first")
            return
        self.hide()
        QTimer.singleShot(250, lambda: self.begin_selection(purpose))

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

    def screenshot_full(self):
        if self.selector is not None or self.recorder.active:
            return
        self.hide()
        QTimer.singleShot(350, self.finish_full_screenshot)

    def finish_full_screenshot(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            self.show_window()
            self.error("Screenshot", "No screen detected")
            return
        self.save_screenshot(None, screen.grabWindow(0))

    def save_screenshot(self, _rect, pixmap):
        QTimer.singleShot(0, self.clear_selection)
        path = screenshots_dir() / stamped_filename("screenshot", "png")
        if pixmap.isNull() or not pixmap.save(str(path), "PNG"):
            self.show_window()
            self.error("Screenshot", "Could not save screenshot")
            return
        QApplication.clipboard().setImage(pixmap.toImage())
        self.show_window()
        self.inform("Screenshot saved", str(path))
        self.refresh_library("Screenshots")

    def choose_recording(self, file_format: str = "MP4"):
        self.capture_format = file_format if file_format in ("MP4", "GIF") else "MP4"
        self.select_area("video")

    def start_video(self, rect, _pixmap):
        QTimer.singleShot(0, self.clear_selection)
        self.capture_rect = rect
        # Main ClipMint remains hidden, and the selection overlay has exited.
        QTimer.singleShot(300, self.show_recorder)

    def show_recorder(self):
        self.recorder_window = RecorderWindow(self.capture_rect, self.capture_format)
        self.recorder_window.start_requested.connect(self.launch_recorder)
        self.recorder_window.stop_requested.connect(self.stop_recording)
        self.recorder_window.cancelled.connect(self.cancel_recorder)
        self.recorder_window.place_outside()
        self.update_buttons()

    def cancel_recorder(self):
        if self.recorder.process is None:
            self.recorder_window = None
            self.show_window()

    def launch_recorder(self, quality: str, file_format: str):
        try:
            path = self.recorder.start(self.capture_rect, quality, file_format)
        except Exception as exc:
            if self.recorder_window:
                self.recorder_window.start_failed()
            self.error("Recording", str(exc))
            return
        if self.recorder_window:
            self.recorder_window.recording_started(path, self.recorder.estimated_bytes_per_second)
        self.update_buttons()

    def stop_recording(self):
        if self.recorder.stop():
            self.statusBar().showMessage("Finalizing recording; please keep ClipMint open")
        elif self.recorder.process is None:
            self.inform("Recording", "No active recording")
        self.update_buttons()

    def poll_recording(self):
        result = self.recorder.finished()
        if result is None:
            return
        status, path = result
        recorder_window = self.recorder_window
        duration = recorder_window.timer_label.text() if recorder_window else "00:00:00"
        if recorder_window is not None:
            recorder_window.recording_finished()
            recorder_window.deleteLater()
            self.recorder_window = None
        self.update_buttons()
        if status == 0 and path and path.exists() and path.stat().st_size:
            dialog = SaveClipDialog(path, duration, self.recorder.quality)
            save = dialog.exec() == QDialog.DialogCode.Accepted
            try:
                result_path = RegionRecorder.resolve(path, save)
                if result_path:
                    self.inform("Recording saved", str(result_path))
                else:
                    self.inform("Recording discarded", "Temporary clip deleted")
            except OSError as exc:
                self.error("Recording file", str(exc))
        else:
            self.error("Recording error", "FFmpeg failed; check the .ffmpeg.log in Videos/ClipMint")
        self.show_window()
        self.refresh_library("Recordings")

    def update_buttons(self):
        busy = self.recorder.process is not None or self.recorder_window is not None
        self.record_button.setEnabled(not busy)
        self.record_menu.setEnabled(not busy)
        if self.tray_stop is not None:
            self.tray_stop.setEnabled(self.recorder.active and not self.recorder.stopping)

    def open_path(self, path: Path):
        try:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError as exc:
            self.error("Open", str(exc))

    def open_folder(self, folder: Path):
        self.open_path(folder)

    def closeEvent(self, event):
        if self._closing:
            event.accept()
        elif self.tray is not None:
            self.hide()
            event.ignore()
        elif self.recorder.process is not None:
            self.error("Recording active", "Finish recording before quitting")
            event.ignore()
        else:
            self.store.close()
            event.accept()

    def quit_app(self):
        if self.recorder.process is not None:
            self.error("Recording active", "Finish recording before quitting")
            return
        if self.recorder_window is not None:
            self.recorder_window.hide()
            self.recorder_window.deleteLater()
            self.recorder_window = None
        self._closing = True
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
                            "ClipMint currently requires an X11 session (e.g. Cinnamon X11).")
        raise SystemExit(1)
    window = ClipMintWindow()
    window.show()
    raise SystemExit(app.exec())
