"""ClipMint: self-contained, mouse-first clipboard bins and screen capture for Cinnamon X11."""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys

from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice, QTimer
from PySide6.QtGui import QImage, QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QPushButton, QStyle, QSystemTrayIcon,
    QTabBar, QToolButton, QVBoxLayout, QWidget, QStackedWidget, QSizePolicy,
)

from .branding import ChromaticWordmark, register_display_font
from .capture import AreaSelector, RegionRecorder, recordings_dir, screenshots_dir, stamped_filename
from .recording_ui import RecorderWindow, SaveClipDialog
from .store import ClipStore, classify, looks_sensitive


THEME = """
/* Native Qt style: tonal elevation, clear hierarchy, restrained accent strokes. */
QMainWindow, QWidget#appRoot {background:#080B10;color:#F1F5F9;
    font-family:"DejaVu Sans";font-size:14px;}
QLabel {color:#F1F5F9;font-family:"DejaVu Sans";font-size:14px;}
QLabel#edition {color:#FF5AB3;font-family:"DotGothic16";font-size:14px;}
QLabel#muted {color:#94A3B8;font-size:12px;}
QLabel#sectionTitle {color:#F1F5F9;font-family:"DotGothic16";font-size:19px;}
QLabel#previewHeading {color:#FF5AB3;font-family:"DotGothic16";font-size:15px;}
QLabel#previewDimensions {color:#94A3B8;font-size:12px;}
QLineEdit,QComboBox {font-family:"DejaVu Sans";font-size:14px;
    background:#131C2D;color:#F1F5F9;border:1px solid #253346;
    padding:10px;border-radius:8px;selection-background-color:#226E59;}
QLineEdit:focus,QComboBox:focus {border:1px solid #00FF9D;}
QListWidget {font-family:"DejaVu Sans";font-size:14px;
    background:#131C2D;color:#F1F5F9;border:0px;
    border-radius:10px;padding:8px;outline:none;}
QListWidget::item {padding:11px 9px;border:0px;}
QListWidget::item:hover {background:#1A263C;border-radius:7px;}
QListWidget::item:selected {background:#164435;border-radius:7px;}
QPushButton,QToolButton {font-family:"DejaVu Sans";font-size:13px;
    background:#131C2D;color:#F1F5F9;border:0px;
    border-radius:8px;padding:11px 12px;font-weight:600;}
QPushButton:hover,QToolButton:hover {background:#1A263C;}
QPushButton:focus,QToolButton:focus {border:1px solid #00FF9D;}
QPushButton:checked {background:#164435;}
QPushButton#nav {font-family:"DotGothic16";font-size:14px;text-align:left;background:transparent;border:0px;
    border-left:3px solid transparent;border-radius:0px;padding:12px 13px;}
QPushButton#nav:hover {background:#1A263C;}
QPushButton#nav:checked {background:#112B24;border-left:3px solid #00FF9D;color:#F1F5F9;}
QPushButton#record {background:#105341;color:#F1F5F9;font-size:14px;}
QPushButton#record:hover {background:#156B53;}
QPushButton#screenshot {background:#35214C;color:#F1F5F9;font-size:14px;}
QPushButton#screenshot:hover {background:#492D66;}
QTabBar::tab {font-family:"DotGothic16";font-size:15px;
    background:transparent;color:#94A3B8;border:0px;
    border-bottom:2px solid transparent;
    padding:12px 17px;border-radius:0px;margin-right:6px;}
QTabBar::tab:hover {color:#F1F5F9;}
QTabBar::tab:selected {color:#F1F5F9;border-bottom:2px solid #00FF9D;}
QFrame#sidebar {background:#0D131F;border:0px;border-radius:10px;}
QFrame#preview {background:#0D131F;border:0px;border-radius:10px;}
QStatusBar {font-family:"DejaVu Sans";font-size:12px;
    background:#0D131F;color:#94A3B8;border:0px;}
"""


class ImagePreviewLabel(QLabel):
    """Fit an in-memory thumbnail to the pane without altering the saved clip."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._original: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)

    def show_image(self, image: QImage) -> None:
        self._original = QPixmap.fromImage(image)
        self._update_size()

    def clear_image(self) -> None:
        self._original = None
        self.clear()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_size()

    def _update_size(self) -> None:
        if self._original is not None and not self._original.isNull():
            if self.width() > 0 and self.height() > 0:
                preview = self._original.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.setPixmap(preview)


class ClipMintWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClipMint · Clipboard & Capture")
        self.brand_family = register_display_font()
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
        # Uneven, screen-printed chromatic registration is limited to the brand.
        self.wordmark = ChromaticWordmark(self.brand_family)
        header.addWidget(self.wordmark)
        edition = QLabel("VE / 02")
        edition.setObjectName("edition")
        header.addWidget(edition)
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
            b = QPushButton(name.replace("&", "&&"))
            b.setObjectName("nav")
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
        self.screenshot_button = QPushButton("▣  Screenshot Area")
        self.screenshot_button.setObjectName("screenshot")
        self.screenshot_button.clicked.connect(self.choose_screenshot)
        footer.addWidget(self.screenshot_button, 2)
        self.screenshot_menu = QToolButton()
        self.screenshot_menu.setText("▾")
        self.screenshot_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        captures = QMenu(self.screenshot_menu)
        captures.addAction("Select area (default)").triggered.connect(self.choose_screenshot)
        captures.addAction("Full screen").triggered.connect(self.screenshot_full)
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
        self.count_label.setObjectName("sectionTitle")
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
        preview_heading = QLabel("PREVIEW")
        preview_heading.setObjectName("previewHeading")
        right.addWidget(preview_heading)
        self.preview_stack = QStackedWidget()
        self.preview_label = QLabel("Select an item to preview")
        self.preview_label.setWordWrap(True)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.preview_stack.addWidget(self.preview_label)
        self.preview_image_page = QWidget()
        image_layout = QVBoxLayout(self.preview_image_page)
        image_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_image = ImagePreviewLabel()
        image_layout.addWidget(self.preview_image, 1)
        self.preview_dimensions = QLabel("")
        self.preview_dimensions.setObjectName("previewDimensions")
        self.preview_dimensions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.preview_dimensions)
        self.preview_stack.addWidget(self.preview_image_page)
        right.addWidget(self.preview_stack, 1)
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
        heading.setObjectName("sectionTitle")
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
        heading.setObjectName("sectionTitle")
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
            self.clear_preview()

    def clear_preview(self) -> None:
        self.preview_image.clear_image()
        self.preview_label.setText("Select an item to preview")
        self.preview_stack.setCurrentWidget(self.preview_label)

    def preview_clip(self, current, _old):
        if current is None:
            self.clear_preview()
            return
        value = self.store.get(current.data(Qt.ItemDataRole.UserRole))
        if value is None:
            self.clear_preview()
            return
        kind, contents = value
        if kind == "text":
            self.preview_image.clear_image()
            self.preview_label.setText(contents.decode("utf-8", errors="replace")[:5000])
            self.preview_stack.setCurrentWidget(self.preview_label)
            return
        if len(contents) > 16 * 1024 * 1024:
            self.preview_label.setText("Image too large to preview")
            self.preview_stack.setCurrentWidget(self.preview_label)
            return
        # PNG dimensions are big-endian at bytes 16–23. Limit decompression
        # before decoding potentially untrusted images from clipboard history.
        if contents.startswith(b"\x89PNG\r\n\x1a\n") and len(contents) >= 24:
            width = int.from_bytes(contents[16:20], "big")
            height = int.from_bytes(contents[20:24], "big")
            if not width or not height or width * height > 32_000_000:
                self.preview_label.setText("Image dimensions exceed safe preview limits")
                self.preview_stack.setCurrentWidget(self.preview_label)
                return
        image = QImage.fromData(contents, "PNG")
        if image.isNull():
            self.preview_label.setText("Unable to preview this image")
            self.preview_stack.setCurrentWidget(self.preview_label)
            return
        self.preview_dimensions.setText(f"{image.width()} × {image.height()} pixels")
        self.preview_stack.setCurrentWidget(self.preview_image_page)
        self.preview_image.show_image(image)

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
            self.selector = AreaSelector(purpose)
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
