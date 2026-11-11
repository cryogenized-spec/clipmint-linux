"""Capture archive presentation for screenshots and local recordings.

Only gallery widgets, thumbnail previews, and saved-file actions live here.
The main window retains capture/recording lifecycle, persisted history, OCR
workers, and ownership of UI state. Qt callbacks keep their original names.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer, QMimeData
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFrame, QHBoxLayout, QLabel, QListView, QListWidget,
    QListWidgetItem, QMenu, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .capture import recordings_dir, screenshots_dir
from .screenshot_gallery import (
    PREVIEW_SIZE, read_screenshot, screenshot_thumbnail_icon,
)


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


class LibraryControllerMixin:
    """Screenshot and recording archive Qt UI and saved-file operations."""

    def build_library_page(self, kind: str):
        page = QWidget()
        page.setObjectName("captureLibraryPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 17, 18, 17)
        layout.setSpacing(10)

        eyebrow = QLabel("ARCHIVE / SCREENSHOTS" if kind == "Screenshots"
                         else "ARCHIVE / RECORDINGS")
        eyebrow.setObjectName("captureEyebrow")
        layout.addWidget(eyebrow)
        heading = QLabel("Screenshot archive" if kind == "Screenshots"
                         else "Recording archive")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        hint = QLabel("Select an image to inspect it here. Double-click to open it."
                      if kind == "Screenshots"
                      else "Your locally recorded MP4 and GIF files.")
        hint.setObjectName("captureHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        listing = QListWidget()
        listing.itemDoubleClicked.connect(self.open_saved_file)
        if kind == "Screenshots":
            listing.setObjectName("screenshotGallery")
            listing.setViewMode(QListView.ViewMode.IconMode)
            listing.setResizeMode(QListView.ResizeMode.Adjust)
            listing.setMovement(QListView.Movement.Static)
            listing.setWrapping(True)
            listing.setWordWrap(True)
            listing.setIconSize(QSize(204, 126))
            listing.setGridSize(QSize(230, 172))
            listing.setSpacing(6)
            listing.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            listing.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            listing.customContextMenuRequested.connect(self.screenshot_context_menu)
            listing.currentItemChanged.connect(
                lambda item, _previous: self.preview_saved_screenshot(item)
            )

            content = QHBoxLayout()
            content.setSpacing(12)
            content.addWidget(listing, 3)

            panel = QFrame()
            panel.setObjectName("capturePreviewPane")
            panel.setMinimumWidth(220)
            panel.setMaximumWidth(410)
            details = QVBoxLayout(panel)
            details.setContentsMargins(12, 12, 12, 12)
            details.setSpacing(9)
            title = QLabel("SELECTED FRAME / プレビュー")
            title.setObjectName("captureEyebrow")
            details.addWidget(title)

            self.screenshot_preview_image = ImagePreviewLabel()
            self.screenshot_preview_image.setObjectName("screenshotLargePreview")
            self.screenshot_preview_image.setMinimumHeight(165)
            details.addWidget(self.screenshot_preview_image, 1)
            self.screenshot_filename = QLabel("Select a screenshot")
            self.screenshot_filename.setWordWrap(True)
            self.screenshot_filename.setObjectName("captureFilename")
            details.addWidget(self.screenshot_filename)
            self.screenshot_details = QLabel("No screenshot selected")
            self.screenshot_details.setObjectName("captureDetails")
            self.screenshot_details.setWordWrap(True)
            details.addWidget(self.screenshot_details)

            actions = QHBoxLayout()
            actions.setSpacing(6)
            for label, handler in (
                ("Open", self.open_selected_screenshot),
                ("Edit", self.edit_selected_screenshot),
                ("OCR", self.ocr_selected_screenshot),
            ):
                button = QPushButton(label)
                button.setObjectName("captureAction")
                button.clicked.connect(handler)
                actions.addWidget(button)
            details.addLayout(actions)
            content.addWidget(panel, 2)
            layout.addLayout(content, 1)
            self.screenshot_count = QLabel("0 screenshots")
            self.screenshot_count.setObjectName("captureDetails")
            layout.addWidget(self.screenshot_count)
        else:
            listing.setObjectName("recordingLibrary")
            layout.addWidget(listing, 1)

        path = screenshots_dir() if kind == "Screenshots" else recordings_dir()
        bottom = QHBoxLayout()
        refresh = QPushButton("Refresh archive")
        refresh.setObjectName("captureAction")
        refresh.clicked.connect(lambda: self.refresh_library(kind))
        bottom.addWidget(refresh)
        folder = QPushButton("Open folder")
        folder.setObjectName("captureAction")
        folder.clicked.connect(lambda: self.open_folder(path))
        bottom.addWidget(folder)
        bottom.addStretch()
        layout.addLayout(bottom)
        if not hasattr(self, "libraries"):
            self.libraries = {}
        self.libraries[kind] = listing
        self.pages.addWidget(page)

    def refresh_library_if_changed(self, kind: str):
        """Avoid repeatedly rescanning/decoding the same capture directory.

        Directory metadata changes when files are added, deleted or renamed.
        The explicit Refresh archive button remains unconditional for external
        in-place image edits, which don't necessarily alter directory mtime.
        """
        folder = screenshots_dir() if kind == "Screenshots" else recordings_dir()
        try:
            stamp = (str(folder), folder.stat().st_mtime_ns)
        except OSError:
            self.refresh_library(kind)
            return
        if getattr(self, "_library_scan_stamps", {}).get(kind) == stamp:
            return
        self.refresh_library(kind)

    def refresh_library(self, kind: str, select_path: Path | None = None):
        listing = self.libraries[kind]
        current = listing.currentItem()
        selected_path = (str(select_path) if select_path is not None
                         else current.data(Qt.ItemDataRole.UserRole) if current else None)
        if kind == "Screenshots":
            self._screenshot_thumbnail_generation += 1
            generation = self._screenshot_thumbnail_generation
        else:
            generation = -1
        listing.blockSignals(True)
        listing.clear()
        folder = screenshots_dir() if kind == "Screenshots" else recordings_dir()
        formats = (".png",) if kind == "Screenshots" else (".mp4", ".gif")
        # Files may disappear mid-refresh (e.g. renamed by the image editor).
        dated_paths = []
        for candidate in folder.iterdir():
            try:
                if (candidate.suffix.lower() in formats
                        and not candidate.name.startswith(".")
                        and candidate.is_file()):
                    dated_paths.append((candidate.stat().st_mtime, candidate))
            except OSError:
                continue
        dated_paths.sort(key=lambda pair: pair[0], reverse=True)
        paths = [path for _modified, path in dated_paths]
        thumbnail_rows = []
        preferred = None
        for path in paths:
            item = QListWidgetItem(path.stem if kind == "Screenshots" else path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(path.name)
            listing.addItem(item)
            if kind == "Screenshots":
                thumbnail_rows.append((item, path))
            if selected_path == str(path):
                preferred = item
        listing.blockSignals(False)
        if kind == "Screenshots":
            self.screenshot_count.setText(
                f"{len(paths)} saved screenshot{'s' if len(paths) != 1 else ''}"
            )
            if preferred is None and listing.count():
                preferred = listing.item(0)
            if preferred is not None:
                listing.setCurrentItem(preferred)
            else:
                self.preview_saved_screenshot(None)
            self._paint_screenshot_thumbnails(thumbnail_rows, generation)
        # Store the stamp after the scan, including explicit refreshes and
        # newly captured screenshots. Invalidates automatically on directory
        # changes without touching any thumbnail cache on disk.
        try:
            stamp = (str(folder), folder.stat().st_mtime_ns)
        except OSError:
            stamp = None
        if not hasattr(self, "_library_scan_stamps"):
            self._library_scan_stamps = {}
        if stamp is None:
            self._library_scan_stamps.pop(kind, None)
        else:
            self._library_scan_stamps[kind] = stamp

    def _paint_screenshot_thumbnails(self, rows, generation: int):
        """Decode in small event-loop batches so large archives stay responsive."""
        if generation != self._screenshot_thumbnail_generation:
            return
        listing = self.libraries.get("Screenshots")
        for item, path in rows[:8]:
            if item.listWidget() is not listing:
                continue
            icon = screenshot_thumbnail_icon(path)
            if icon is not None:
                item.setIcon(icon)
        if len(rows) > 8:
            QTimer.singleShot(0, lambda: self._paint_screenshot_thumbnails(
                rows[8:], generation
            ))

    def preview_saved_screenshot(self, item):
        preview = self.screenshot_preview_image
        preview.clear_image()
        if item is None:
            self.screenshot_filename.setText("Select a screenshot")
            self.screenshot_details.setText("No screenshot selected")
            return
        target = Path(item.data(Qt.ItemDataRole.UserRole))
        self.screenshot_filename.setText(target.name)
        result = read_screenshot(target, PREVIEW_SIZE)
        if result is None:
            self.screenshot_details.setText("Preview unavailable · use Open folder")
            return
        image, dimensions = result
        preview.show_image(image)
        try:
            size_kib = target.stat().st_size / 1024
        except OSError:
            size_kib = 0
        self.screenshot_details.setText(
            f"{dimensions.width()} × {dimensions.height()} px   ·   {size_kib:,.0f} KiB"
        )

    def selected_screenshot_path(self) -> Path | None:
        listing = self.libraries.get("Screenshots")
        item = listing.currentItem() if listing is not None else None
        if item is None:
            return None
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        return path if path.is_file() and path.suffix.lower() == ".png" else None

    def open_selected_screenshot(self):
        path = self.selected_screenshot_path()
        if path is not None:
            self.open_path(path)

    def edit_selected_screenshot(self):
        path = self.selected_screenshot_path()
        if path is not None:
            self._last_screenshot_path = path
            self.edit_last_screenshot()

    def ocr_selected_screenshot(self):
        path = self.selected_screenshot_path()
        if path is not None:
            self.start_ocr_file(path)

    def copy_selected_screenshot(self) -> bool:
        """Copy the full-resolution, bounded PNG, not its gallery thumbnail."""
        path = self.selected_screenshot_path()
        if path is None or path.is_symlink():
            return False
        result = read_screenshot(path, QSize(18000, 18000))
        if result is None:
            self.error("Copy image", "The selected PNG cannot be safely read.")
            return False
        image, _dimensions = result
        try:
            png = path.read_bytes()
        except OSError:
            self.error("Copy image", "The selected PNG is no longer readable.")
            return False
        mime = QMimeData()
        mime.setData("image/png", png)
        mime.setImageData(image)
        # Suppress re-ingesting our own clipboard write as a second entry.
        self._own_clipboard_guard.note_entry("image", png)
        QApplication.clipboard().setMimeData(mime)
        self.inform("Image copied", path.name)
        return True

    def open_saved_file(self, item):
        target = Path(item.data(Qt.ItemDataRole.UserRole))
        if target.is_file():
            self.open_path(target)

    def screenshot_context_menu(self, position):
        listing = self.libraries.get("Screenshots")
        if listing is None:
            return
        item = listing.itemAt(position)
        if item is None:
            return
        target = Path(item.data(Qt.ItemDataRole.UserRole))
        listing.setCurrentItem(item)
        menu = QMenu(self)
        copy = menu.addAction("Copy image")
        ocr = menu.addAction("OCR · Extract text")
        edit = menu.addAction("Open in image editor")
        choice = menu.exec(listing.viewport().mapToGlobal(position))
        if choice == copy:
            self.copy_selected_screenshot()
        elif choice == ocr:
            self.start_ocr_file(target)
        elif choice == edit:
            self._last_screenshot_path = target
            self.edit_last_screenshot()

