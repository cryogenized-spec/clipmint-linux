"""ClipMint: self-contained, mouse-first clipboard bins and screen capture for Cinnamon X11."""
from __future__ import annotations

from pathlib import Path
import json
import os
import shlex
import sqlite3
import subprocess
import sys

from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice, QTimer, QSettings, QSize
from PySide6.QtGui import QImage, QFont, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QPushButton, QStyle, QSystemTrayIcon,
    QTabBar, QToolButton, QVBoxLayout, QWidget, QStackedWidget, QSizePolicy,
    QKeySequenceEdit, QGroupBox, QCheckBox, QDialogButtonBox, QTabWidget,
    QFormLayout, QAbstractItemView, QFileDialog, QScrollArea, QListView,
)

from .branding import ChromaticWordmark, register_display_font
from .manga import CrimsonMaidPortrait
from .crimson_ui import build_crimson_ui, relative_time, label_type
from .capture import AreaSelector, RegionRecorder, recordings_dir, screenshots_dir, stamped_filename
from .recording_ui import RecorderWindow
from .recording_controller import RecordingControllerMixin
from .store import ClipStore, classify, looks_sensitive
from .autosort import RULE_TYPES, NEVER_CAPTURE, validate_rule, route_clip
from .smart_types import (SMART_TYPES, TYPE_BY_KEY, DEFAULT_BINS as SMART_BINS,
                          classify_smart, default_smart_rules)
from .vault import Vault
from .vault_controller import VaultControllerMixin
from .autosort_controller import AutosortControllerMixin
from .screenshot_editor import installed_editors, resolve_editor, open_image_editor
from .screenshot_notice import ScreenshotNotice, play_capture_sound
from .screenshot_gallery import read_screenshot, screenshot_thumbnail_icon, PREVIEW_SIZE
from .clipboard_formats import from_mime, is_concealed, sensitive_text, mime_from_entry
from .clipboard_guard import OwnClipboardGuard, HiddenTextClipboardProbe
from .foreground_privacy import blocked_foreground, DEFAULT_BLOCKED
from .ocr import OcrWorker, validate_language
from .quick_popup import QuickPopup, paste_to_window
from .productivity import PasteQueue
from .organizer_ui import TemplatesDialog, TransformDialog
from .history_filters import populate_filter_tabs, selected_category
from .updater import installed_version, PreviewUpdate
from .update_controller import UpdateControllerMixin, UpdateSignals
from .history_controller import HistoryControllerMixin
from .single_instance import InstanceServer, send_command
from .cinnamon_hotkey import (install_shortcut, restore_screenshot_takeover,
                              shortcut_conflicts, ShortcutSetupError)
from .secure_history import (EncryptedClipStore, HistorySecurityError,
                             key_from_secret_service, secure_path)
from .archive_backup import backup_archive, ArchiveBackupError
from .legacy_cleanup import verify_legacy_history, remove_verified_legacy_history
from .autostart import AutostartError, is_enabled as login_startup_enabled, set_enabled as set_login_startup


THEME = """
/* Native Qt style: tonal elevation, clear hierarchy, restrained accent strokes. */
QMainWindow, QWidget#appRoot {background:#080B10;color:#F1F5F9;
    font-family:"DejaVu Sans";font-size:14px;}
QLabel {color:#F1F5F9;font-family:"DejaVu Sans";font-size:14px;}
QLabel#edition {color:#FF5AB3;font-family:"DotGothic16";font-size:14px;}
QLabel#kanaTag {color:#B9FF45;font-family:"DotGothic16";font-size:16px;}
QLabel#maidTag {color:#FF5AB3;font-family:"DotGothic16";font-size:14px;}
QLabel#maidMeta {color:#94A3B8;font-family:"DejaVu Sans Mono";font-size:9px;}
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


# These are WINDOW shortcuts: they never grab keys from other applications.
# A blank saved sequence means the individual action is disabled.
SHORTCUT_SPECS = (
    ("search", "Focus clipboard search", "Ctrl+F"),
    ("screenshot", "Select screenshot area", "Ctrl+Shift+S"),
    ("record", "Select video recording area", "Ctrl+Shift+R"),
    ("copy", "Copy selected history item", "Ctrl+Shift+C"),
    ("monitor", "Pause / resume clipboard monitoring", "Ctrl+Shift+M"),
)


class WheelSafeHistoryLimitComboBox(QComboBox):
    """Wheel scrolling a Settings page must not alter a destructive setting.

    A closed QComboBox normally selects another value on wheelEvent; that
    would raise a permanent-deletion confirmation while the user simply
    scrolls the Settings QScrollArea. Require an actual click or keyboard
    selection. Wheel events bubble up to the containing scroll area.
    """

    def wheelEvent(self, event):
        event.ignore()


class ClipMintWindow(HistoryControllerMixin, UpdateControllerMixin, AutosortControllerMixin, VaultControllerMixin, RecordingControllerMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClipMint · Clipboard & Capture")
        self.brand_family = register_display_font()
        self.resize(1300, 870)
        self.setMinimumSize(850, 600)
        self.store = ClipStore()
        self.settings = QSettings("ClipMint", "ClipMint")
        self._temporary_exit_cleaned = False
        self._update_busy = False
        self._verified_update_path = None
        self._available_update: PreviewUpdate | None = None
        self._update_signals = UpdateSignals(self)
        self._update_signals.finished.connect(self._on_update_result)
        self._auto_update_timer = QTimer(self)
        self._auto_update_timer.setInterval(6 * 60 * 60 * 1000)
        self._auto_update_timer.timeout.connect(self._auto_check_updates)
        self._temporary_expiry_timer = QTimer(self)
        self._temporary_expiry_timer.setInterval(5 * 60 * 1000)
        self._temporary_expiry_timer.timeout.connect(self.expire_temporary_if_enabled)
        self.history_secure = False
        self.history_security_error = ""
        self.history_integrity_warning = ""
        if self.settings.value("privacy/history_secure", False, type=bool):
            try:
                if not secure_path().is_file():
                    raise HistorySecurityError("Encrypted history file not found")
                key = key_from_secret_service(create=False)
                encrypted = EncryptedClipStore(secure_path(), key)
                self.store.close()
                self.store = encrypted
                self.history_secure = True
                if encrypted.corrupt_row_ids:
                    self.history_integrity_warning = (
                        f"Warning: {len(encrypted.corrupt_row_ids)} unreadable "
                        "encrypted history item(s) hidden, not deleted."
                    )
            except (HistorySecurityError, OSError) as exc:
                self.history_security_error = str(exc)
        history_mb = self.settings.value("history/max_total_mb", 0, type=int)
        self.store.max_total_bytes = (
            history_mb * 1024 * 1024
            if history_mb in (128, 256, 512, 1024) else None
        )
        # Seed new installations with ready-to-use Smart collections, but do
        # not alter existing rule sets or overwrite a deliberate disabled state.
        if (not self.history_security_error
                and not self.settings.contains("autosort/rules")):
            for name in SMART_BINS:
                if name not in self.store.bins():
                    self.store.add_bin(name)
        self.vault = Vault()
        self._vault_clipboard_text = None
        self._vault_clipboard_token = 0
        self._sensitive_clipboard_token = 0
        self._vault_lock_timer = QTimer(self)
        self._vault_lock_timer.setSingleShot(True)
        self._vault_lock_timer.timeout.connect(self.lock_vault)
        self.recorder = RegionRecorder()
        # Decryption is deliberately synchronous and ephemeral. Debounce
        # rapid text edits to avoid decrypting up to 1,000 rows per keystroke.
        self._history_search_timer = QTimer(self)
        self._history_search_timer.setSingleShot(True)
        self._history_search_timer.setInterval(180)
        self._history_search_timer.timeout.connect(self.refresh)
        self.monitoring = not bool(self.history_security_error)
        self.selector: AreaSelector | None = None
        self.recorder_window: RecorderWindow | None = None
        self.capture_rect = None
        self.capture_scale = None
        self.capture_origin = None
        self.capture_format = "MP4"
        self._privacy_skipped = 0
        self._closing = False
        self._own_clipboard_guard = OwnClipboardGuard()
        self._hidden_text_probe = HiddenTextClipboardProbe()
        self._hidden_clipboard_timer = QTimer(self)
        self._hidden_clipboard_timer.setInterval(1500)
        self._hidden_clipboard_timer.timeout.connect(self.poll_hidden_clipboard)
        self._last_screenshot_path = None
        self._capture_restore_main = False
        self._screenshot_thumbnail_generation = 0
        self._ocr_workers = set()
        self._last_tray_notification = None
        self._screenshot_notice_token = 0
        self.screenshot_notice = None

        # Native reconstruction of the approved Crimson Archive v2 prototype.
        # All content comes from the existing history store and capture methods.
        self.paste_queue = PasteQueue()
        self.wordmark = ChromaticWordmark(self.brand_family)
        build_crimson_ui(self, ImagePreviewLabel)
        self.build_library_page("Screenshots")
        self.build_library_page("Recordings")
        self.build_vault_page()
        self.build_autosort_page()
        self.build_settings_page()
        self.install_shortcuts()
        self.quick_popup = QuickPopup(self.store, self.quick_pick)
        self.statusBar().showMessage(
            self.history_security_error or self.history_integrity_warning or
            "Ready · Left-click to preview, right-click for Copy / Pin / Move / Delete"
        )
        self.configure_tray()
        self.screenshot_notice = ScreenshotNotice(
            self, self.edit_last_screenshot, self.dismiss_screenshot_notice,
            on_ocr=self.ocr_last_screenshot,
        )
        # Every clipboard replacement invalidates earlier sensitive expiry
        # deadlines, even when history monitoring skips or suppresses a copy.
        QApplication.clipboard().dataChanged.connect(
            self._clipboard_generation_changed
        )
        QApplication.clipboard().dataChanged.connect(self.clipboard_changed)
        # Starting the watcher must not retroactively import text copied
        # while ClipMint was explicitly QUIT. Observe the current clipboard
        # as a baseline, then capture future changes through dataChanged
        # and the hidden-window recovery timer.
        self._hidden_text_probe.observe(QApplication.clipboard().mimeData())
        # Keep observing the most recent plain-text clip after the archive is
        # closed, even if a Cinnamon/X11 clipboard manager misses a signal.
        # This is a fallback for a LIVE hidden process, not a background
        # service that can run after the user explicitly chooses Quit.
        self._hidden_clipboard_timer.start()
        self.poller = QTimer(self)
        self.poller.timeout.connect(self.poll_recording)
        self.poller.start(300)
        self.open_section(0)
        self._update_manga_visibility()
        self.update_temporary_expiry_schedule()
        # Only an explicitly saved enabled setting can trigger cleanup on
        # startup. An upgrade or an application crash cannot opt users in.
        if self._temporary_expiry_timer.isActive():
            QTimer.singleShot(0, self.expire_temporary_if_enabled)
        # Do not call clipboard_changed() unconditionally at startup: it
        # would save a clip from a period in which monitoring was not active.
        QTimer.singleShot(900, self.offer_pending_recordings)
        if getattr(sys, "frozen", False):
            # Network activity is explicitly configurable and never runs in
            # the Qt UI thread. Development/testing checkouts remain offline
            # unless the user presses Check now.
            self._auto_update_timer.start()
            QTimer.singleShot(12000, self._auto_check_updates)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "manga_dock"):
            self._update_manga_visibility()

    def _update_manga_visibility(self):
        """Keep dock labels readable; never regress to an icons-only rail.

        The character card hides on compact displays so real editing and the
        selected-item preview retain useful width.
        """
        show = self.width() >= 1120 and self.height() >= 700
        self.manga_dock.setVisible(show)
        if show:
            self.manga_dock.setFixedWidth(
                min(390, max(310, int(self.width() * .265)))
            )
        wide = self.width() >= 1180
        self.dock_panel.setFixedWidth(142 if wide else 134)
        if hasattr(self, "archive_heading"):
            self.archive_heading.setText(
                "Clipboard  ·  クリップボード"
                if self.width() >= 1150 else "Clipboard"
            )
        if hasattr(self, "preview_heading"):
            self.preview_heading.setText(
                "プレビュー  Preview"
                if self.width() >= 1190 else "プレビュー"
            )
        for label, button in self.nav_buttons.items():
            display = button.property("dockDisplay") or label
            subtitle = button.property("dockSubtitle") or ""
            icon = button.property("dockIcon") or "◇"
            # Even in the compact layout titles remain visible.
            button.setText(
                f"{icon}  {display}\n   {subtitle}"
                if wide else f"{icon}  {display}"
            )
            button.setMinimumHeight(67 if wide else 49)
            button.setToolTip(f"{display}: {label}")

    def build_clipboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        bins = QHBoxLayout()
        self.tabs = QTabBar()
        self.tabs.setExpanding(True)
        self.tabs.setDrawBase(False)
        # Tabs filter a unified history; none represents a storage folder.
        populate_filter_tabs(self.tabs)
        self.tabs.currentChanged.connect(self.refresh)
        bins.addWidget(self.tabs, 1)
        layout.addLayout(bins)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search all copied content…")
        self.search.textChanged.connect(self._schedule_history_search)
        layout.addWidget(self.search)
        sorts = QHBoxLayout()
        sorts.addWidget(QLabel("Collection:"))
        self.bin_filter = QComboBox()
        self.bin_filter.setObjectName("collectionFilter")
        self.bin_filter.addItem("All collections", None)
        for name in self.store.bins():
            self.bin_filter.addItem(name, name)
        self.bin_filter.currentIndexChanged.connect(self.refresh)
        sorts.addWidget(self.bin_filter)
        add_bin = QPushButton("+")
        add_bin.setToolTip("Create an Autosort collection")
        add_bin.clicked.connect(self.new_bin)
        sorts.addWidget(add_bin)
        sorts.addWidget(QLabel("Sort:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Latest first", "Oldest first", "A–Z", "Z–A", "Best match", "Numbered list"])
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
        self.preview_heading = QLabel("PREVIEW  /  プレビュー")
        self.preview_heading.setObjectName("previewHeading")
        right.addWidget(self.preview_heading)
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

    def build_vault_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel("Secrets & Variables · encrypted local vault")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        warning = QLabel(
            "Vault entries, including names, are encrypted on disk with "
            "libsodium SecretBox and an Argon2id-derived key. Ordinary "
            "clipboard history is NOT encrypted. X11 makes copied values "
            "visible to other local applications until the clipboard clears."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.vault_status = QLabel("")
        layout.addWidget(self.vault_status)
        self.vault_items = QListWidget()
        self.vault_items.itemDoubleClicked.connect(
            lambda _item: self.reveal_vault_value()
        )
        layout.addWidget(self.vault_items, 1)
        auth = QHBoxLayout()
        self.vault_actions = {}
        for name, label, callback in (
            ("create", "Create vault", self.create_vault),
            ("unlock", "Unlock", self.unlock_vault),
            ("lock", "Lock", self.lock_vault),
            ("backup", "Encrypted backup", self.backup_vault),
            ("restore", "Restore backup", self.restore_vault),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(callback)
            auth.addWidget(btn)
            self.vault_actions[name] = btn
        layout.addLayout(auth)
        commands = QHBoxLayout()
        for name, label, callback in (
            ("add", "New entry", self.add_vault_entry),
            ("reveal", "Reveal", self.reveal_vault_value),
            ("copy", "Copy", self.copy_vault_value),
            ("remove", "Delete entry", self.remove_vault_entry),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(callback)
            commands.addWidget(btn)
            self.vault_actions[name] = btn
        layout.addLayout(commands)
        maintenance = QHBoxLayout()
        for name, label, callback in (
            ("rotate", "Change passphrase", self.change_vault_passphrase),
            ("wipe", "Delete vault", self.wipe_vault),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(callback)
            maintenance.addWidget(btn)
            self.vault_actions[name] = btn
        layout.addLayout(maintenance)
        note = QLabel(
            "There is no password reset: retain your passphrase and an "
            "encrypted backup. The vault locks automatically after five "
            "minutes without a vault action. It also locks when ClipMint closes."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.pages.addWidget(page)
        self.refresh_vault()

    def build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Settings · local-only"))
        # The monitoring state must be visible, especially if encrypted
        # history could not be unlocked on restart. Never present a disabled
        # watcher as though it is still actively collecting clipboard clips.
        self.pause_button = QPushButton(
            "Monitoring unavailable · unlock keyring and restart"
            if self.history_security_error else
            "Pause monitoring" if self.monitoring else "Resume monitoring"
        )
        self.pause_button.setEnabled(not bool(self.history_security_error))
        self.pause_button.clicked.connect(self.toggle_monitoring)
        layout.addWidget(self.pause_button)

        login_group = QGroupBox("Start at login")
        login_layout = QVBoxLayout(login_group)
        login_help = QLabel(
            "Optional and OFF by default. Starts the clipboard watcher quietly "
            "when you sign in to Cinnamon/X11. Closing the window keeps history "
            "capture active in the background, even without a tray icon. "
            "Open ClipMint again from the application menu to show the window. "
            "Use Quit ClipMint to stop monitoring completely."
        )
        login_help.setWordWrap(True)
        login_layout.addWidget(login_help)
        self.login_startup_toggle = QCheckBox("Launch ClipMint when I log in")
        self.login_startup_toggle.setChecked(login_startup_enabled())
        self.login_startup_toggle.toggled.connect(self.set_login_startup_enabled)
        login_layout.addWidget(self.login_startup_toggle)
        quit_background_button = QPushButton("Quit ClipMint · stop background monitoring")
        quit_background_button.clicked.connect(self.quit_app)
        login_layout.addWidget(quit_background_button)
        layout.addWidget(login_group)

        update_group = QGroupBox("Updates · verified preview channel")
        update_layout = QVBoxLayout(update_group)
        update_help = QLabel(
            "Manual checking is the default. You may opt in to automatic "
            "checks and VERIFIED DIFFERENTIAL PATCH downloads up to 20 MB "
            "from ClipMint's official preview channel. If a suitable patch "
            "is unavailable, ClipMint will NOT download a full installer "
            "automatically. Full package downloads require your explicit "
            "approval, and installation still requires Linux Mint's "
            "package-manager approval. No automatic sudo or installation."
        )
        update_help.setWordWrap(True)
        update_layout.addWidget(update_help)
        self.auto_update_toggle = QCheckBox(
            "Automatically check and download small verified patches (20 MB max)"
        )
        self.auto_update_toggle.setChecked(
            self.settings.value("updates/automatic", False, type=bool)
        )
        self.auto_update_toggle.toggled.connect(self.set_auto_updates_enabled)
        update_layout.addWidget(self.auto_update_toggle)
        self.update_status = QLabel("Installed version: " + (
            installed_version() or "development build"
        ))
        self.update_status.setWordWrap(True)
        update_layout.addWidget(self.update_status)
        self.check_update_button = QPushButton("Check for verified preview updates")
        self.check_update_button.clicked.connect(
            lambda: self.check_for_updates(manual=True)
        )
        update_layout.addWidget(self.check_update_button)
        self.download_update_button = QPushButton(
            "Download available preview… (confirm data usage)"
        )
        self.download_update_button.setEnabled(False)
        self.download_update_button.clicked.connect(self.download_available_preview)
        update_layout.addWidget(self.download_update_button)
        self.install_update_button = QPushButton(
            "Open verified installer in Linux Mint…"
        )
        self.install_update_button.setEnabled(False)
        self.install_update_button.clicked.connect(self.open_verified_update)
        update_layout.addWidget(self.install_update_button)
        layout.addWidget(update_group)

        temp_group = QGroupBox("Temporary collection · retention")
        temp_layout = QVBoxLayout(temp_group)
        explanation = QLabel(
            "Both options start OFF. Only unpinned clips in Temporary are "
            "eligible. Pinned entries, Work, Personal, and snippets survive. "
            "Closing to the tray, an application update or a crash never "
            "triggers clear-on-exit."
        )
        explanation.setWordWrap(True)
        temp_layout.addWidget(explanation)
        self.temporary_expiry_toggle = QCheckBox(
            "Automatically remove unpinned Temporary clips after 24 hours"
        )
        self.temporary_expiry_toggle.setChecked(
            self.settings.value("temporary/expire_24h", False, type=bool)
        )
        self.temporary_expiry_toggle.toggled.connect(
            self.set_temporary_expiry_enabled
        )
        temp_layout.addWidget(self.temporary_expiry_toggle)
        self.temporary_exit_toggle = QCheckBox(
            "Clear unpinned Temporary clips when I quit ClipMint"
        )
        self.temporary_exit_toggle.setChecked(
            self.settings.value("temporary/clear_on_quit", False, type=bool)
        )
        self.temporary_exit_toggle.toggled.connect(
            lambda enabled: self.settings.setValue(
                "temporary/clear_on_quit", enabled
            )
        )
        temp_layout.addWidget(self.temporary_exit_toggle)
        layout.addWidget(temp_group)

        cap_group = QGroupBox("History payload storage limit · optional")
        cap_layout = QVBoxLayout(cap_group)
        cap_help = QLabel(
            "OFF by default. Enabling a limit can remove oldest unpinned "
            "history entries across collections, but NEVER pins. This limits "
            "stored payload bytes, not the physical SQLite file size; normal "
            "updates and crashes never opt you into deleting clips."
        )
        cap_help.setWordWrap(True)
        cap_layout.addWidget(cap_help)
        self.history_storage_limit = WheelSafeHistoryLimitComboBox()
        for name, value in (
            ("Off · no automatic byte pruning", 0),
            ("128 MB", 128),
            ("256 MB", 256),
            ("512 MB", 512),
            ("1 GB", 1024),
        ):
            self.history_storage_limit.addItem(name, value)
        saved_mb = int(self.settings.value("history/max_total_mb", 0, type=int))
        self.history_storage_limit.setCurrentIndex(
            max(0, self.history_storage_limit.findData(saved_mb))
        )
        self.history_storage_limit.currentIndexChanged.connect(
            self.set_history_storage_limit
        )
        self.history_storage_limit.setToolTip(
            "Click to choose a limit. Scrolling Settings will not change it."
        )
        cap_layout.addWidget(self.history_storage_limit)
        layout.addWidget(cap_group)

        labels_group = QGroupBox("Clipboard row appearance")
        labels_layout = QVBoxLayout(labels_group)
        labels_help = QLabel(
            "Keep All clips uncluttered. Optional type badges (TXT, URL, IMG, "
            "etc.) and collection prefixes ([Work], [Writing], etc.) can be "
            "shown when needed. This changes only the display, never clip "
            "content, tags, collections, or Autosort rules."
        )
        labels_help.setWordWrap(True)
        labels_layout.addWidget(labels_help)
        self.clip_labels_toggle = QCheckBox(
            "Show labels before entries in All clips"
        )
        self.clip_labels_toggle.setChecked(
            self.settings.value("history/show_clip_labels", False, type=bool)
        )
        self.clip_labels_toggle.toggled.connect(self.set_clip_labels_visible)
        labels_layout.addWidget(self.clip_labels_toggle)
        layout.addWidget(labels_group)

        ocr_group = QGroupBox("Offline OCR language")
        ocr_layout = QVBoxLayout(ocr_group)
        ocr_help = QLabel(
            "Select installed Tesseract language data. Examples: eng (English), "
            "afr (Afrikaans), or eng+afr. Language packs are not downloaded by ClipMint."
        )
        ocr_help.setWordWrap(True)
        ocr_layout.addWidget(ocr_help)
        self.ocr_language_editor = QLineEdit(
            str(self.settings.value("ocr/language", "eng"))
        )
        self.ocr_language_editor.setPlaceholderText("eng")
        self.ocr_language_editor.editingFinished.connect(self.save_ocr_language)
        ocr_layout.addWidget(self.ocr_language_editor)
        layout.addWidget(ocr_group)

        open_files = QPushButton("Open recordings folder")
        open_files.clicked.connect(lambda: self.open_folder(recordings_dir()))
        layout.addWidget(open_files)

        popup_group = QGroupBox("Quick access")
        popup_controls = QVBoxLayout(popup_group)
        popup_help = QLabel(
            "Open a compact search popup without opening ClipMint's main window."
        )
        popup_help.setWordWrap(True)
        popup_controls.addWidget(popup_help)
        popup_test = QPushButton("Show quick search popup")
        popup_test.clicked.connect(self.toggle_quick_popup)
        popup_controls.addWidget(popup_test)
        self.popup_paste_choice = QCheckBox(
            "Paste into the previously focused window after pressing Enter"
        )
        self.popup_paste_choice.setChecked(
            self.settings.value("popup/auto_paste", True, type=bool)
        )
        self.popup_paste_choice.toggled.connect(
            lambda value: self.settings.setValue("popup/auto_paste", value)
        )
        popup_controls.addWidget(self.popup_paste_choice)
        layout.addWidget(popup_group)

        # One home for every hotkey: Cinnamon global + ClipMint-focused local.
        # Keep each Cinnamon registration opt-in and collision-checked.
        shortcuts_section = QGroupBox("Keyboard shortcuts")
        shortcuts_layout = QVBoxLayout(shortcuts_section)
        shortcuts_help = QLabel(
            "Cinnamon global shortcuts work while Firefox or another app is "
            "focused. Register them individually; ClipMint never replaces "
            "existing desktop shortcuts without confirmation. Local "
            "shortcuts below work only when ClipMint is focused."
        )
        shortcuts_help.setWordWrap(True)
        shortcuts_layout.addWidget(shortcuts_help)
        shortcut_tabs = QTabWidget()
        shortcut_tabs.setObjectName("shortcutTabs")
        shortcuts_layout.addWidget(shortcut_tabs)
        global_page = QWidget()
        global_layout = QVBoxLayout(global_page)
        global_layout.setContentsMargins(10, 10, 10, 10)
        global_layout.setSpacing(8)
        shortcut_tabs.addTab(global_page, "Cinnamon · Global")
        local_page = QWidget()
        local_layout = QVBoxLayout(local_page)
        local_layout.setContentsMargins(10, 10, 10, 10)
        shortcut_tabs.addTab(local_page, "Inside ClipMint")

        global_popup_group = QGroupBox("Clipboard popup · Cinnamon global")
        global_popup_layout = QVBoxLayout(global_popup_group)
        self.global_popup_hotkey = QKeySequenceEdit()
        self.global_popup_hotkey.setKeySequence(QKeySequence(str(
            self.settings.value("popup/global_shortcut", "Ctrl+Alt+V")
        )))
        global_popup_layout.addWidget(self.global_popup_hotkey)
        register_button = QPushButton("Register clipboard popup in Cinnamon…")
        register_button.clicked.connect(self.register_cinnamon_hotkey)
        global_popup_layout.addWidget(register_button)
        global_layout.addWidget(global_popup_group)

        global_screenshot_group = QGroupBox("Screenshot area · Cinnamon global")
        global_screenshot_layout = QVBoxLayout(global_screenshot_group)
        global_screenshot_help = QLabel(
            "The chosen key starts region capture even when ClipMint is hidden. "
            "A conflict with Cinnamon's own screenshot binding can be "
            "replaced only with explicit permission and a reversible backup."
        )
        global_screenshot_help.setWordWrap(True)
        global_screenshot_layout.addWidget(global_screenshot_help)
        self.global_screenshot_hotkey = QKeySequenceEdit()
        self.global_screenshot_hotkey.setKeySequence(QKeySequence(str(
            self.settings.value("capture/global_shortcut", "Ctrl+Shift+S")
        )))
        global_screenshot_layout.addWidget(self.global_screenshot_hotkey)
        screenshot_register = QPushButton("Register screenshot shortcut in Cinnamon…")
        screenshot_register.setObjectName("captureAction")
        screenshot_register.clicked.connect(self.register_cinnamon_screenshot_hotkey)
        global_screenshot_layout.addWidget(screenshot_register)
        restore_screenshot = QPushButton("Restore previous Cinnamon screenshot binding…")
        restore_screenshot.clicked.connect(self.restore_cinnamon_screenshot_hotkey)
        global_screenshot_layout.addWidget(restore_screenshot)
        global_layout.addWidget(global_screenshot_group)

        global_record_group = QGroupBox("Recording area · Cinnamon global")
        global_record_layout = QVBoxLayout(global_record_group)
        global_record_help = QLabel(
            "Choose a system-wide MP4 region-recording key. Other Cinnamon "
            "or custom shortcuts are never silently replaced."
        )
        global_record_help.setWordWrap(True)
        global_record_layout.addWidget(global_record_help)
        self.global_record_hotkey = QKeySequenceEdit()
        self.global_record_hotkey.setKeySequence(QKeySequence(str(
            self.settings.value("capture/global_record_shortcut", "Ctrl+Shift+R")
        )))
        global_record_layout.addWidget(self.global_record_hotkey)
        global_record_button = QPushButton("Register recording shortcut in Cinnamon…")
        global_record_button.clicked.connect(self.register_cinnamon_recording_hotkey)
        global_record_layout.addWidget(global_record_button)
        global_layout.addWidget(global_record_group)

        audit_button = QPushButton("Check Cinnamon hotkey assignments…")
        audit_button.clicked.connect(self.audit_global_hotkeys)
        global_layout.addWidget(audit_button)
        layout.addWidget(shortcuts_section)

        privacy_group = QGroupBox("Clipboard privacy")
        privacy_layout = QVBoxLayout(privacy_group)
        privacy_message = QLabel(
            "Concealed hints and credential/card patterns are excluded. "
            "X11 foreground blocklists are best-effort, not security boundaries. "
            + ("Clipboard contents and previews are encrypted at rest; "
               "collection metadata is visible."
               if self.history_secure else
               "Legacy clipboard history is still plaintext until migrated.")
        )
        privacy_message.setWordWrap(True)
        privacy_layout.addWidget(privacy_message)
        self.foreground_blocklist = QLineEdit()
        self.foreground_blocklist.setPlaceholderText(
            "Blocked active-window classes, comma separated"
        )
        self.foreground_blocklist.setText(str(self.settings.value(
            "privacy/blocked_foreground", ", ".join(DEFAULT_BLOCKED)
        )))
        self.foreground_blocklist.editingFinished.connect(
            lambda: self.settings.setValue(
                "privacy/blocked_foreground", self.foreground_blocklist.text()
            )
        )
        privacy_layout.addWidget(self.foreground_blocklist)
        self.secure_history_button = QPushButton(
            "Encrypted history active" if self.history_secure
            else "Encrypt history with desktop keyring…"
        )
        self.secure_history_button.setEnabled(not self.history_secure)
        self.secure_history_button.clicked.connect(self.enable_encrypted_history)
        privacy_layout.addWidget(self.secure_history_button)
        self.remove_legacy_button = QPushButton(
            "Verify and remove old plaintext history…"
        )
        self.remove_legacy_button.setEnabled(
            self.history_secure and
            (self.store.path.with_name("history.sqlite3").exists())
        )
        self.remove_legacy_button.clicked.connect(self.remove_old_plaintext_history)
        privacy_layout.addWidget(self.remove_legacy_button)

        archive_help = QLabel(
            "Save a consistent local copy of your current clipboard archive, "
            "including uncheckpointed SQLite WAL changes. Backups have "
            "owner-only permissions. Plaintext remains plaintext; encrypted "
            "history stays encrypted and requires your original keyring key."
        )
        archive_help.setWordWrap(True)
        privacy_layout.addWidget(archive_help)
        archive_backup_button = QPushButton("Backup clipboard archive…")
        archive_backup_button.clicked.connect(self.backup_clipboard_archive)
        privacy_layout.addWidget(archive_backup_button)
        layout.addWidget(privacy_group)

        screenshot_group = QGroupBox("Screenshot editor")
        screenshot_layout = QVBoxLayout(screenshot_group)
        screenshot_help = QLabel(
            "Click the notification after a capture to edit the saved PNG. "
            "Select an installed editor, or use your system's default image application."
        )
        screenshot_help.setWordWrap(True)
        screenshot_layout.addWidget(screenshot_help)
        self.screenshot_editor_choice = QComboBox()
        self.screenshot_editor_choice.addItem(
            "Automatic · first installed image editor", "auto"
        )
        for key, title in installed_editors():
            self.screenshot_editor_choice.addItem(title, key)
        self.screenshot_editor_choice.addItem(
            "System image application (may be a viewer)", "system"
        )
        saved_editor = str(self.settings.value("capture/editor", "auto"))
        index = self.screenshot_editor_choice.findData(saved_editor)
        self.screenshot_editor_choice.setCurrentIndex(max(0, index))
        self.screenshot_editor_choice.currentIndexChanged.connect(
            lambda _index: self.settings.setValue(
                "capture/editor", self.screenshot_editor_choice.currentData()
            )
        )
        screenshot_layout.addWidget(self.screenshot_editor_choice)
        self.screenshot_sound_toggle = QCheckBox(
            "Play desktop shutter sound when available"
        )
        self.screenshot_sound_toggle.setChecked(
            self.settings.value("capture/sound_enabled", True, type=bool)
        )
        self.screenshot_sound_toggle.toggled.connect(
            lambda enabled: self.settings.setValue("capture/sound_enabled", enabled)
        )
        screenshot_layout.addWidget(self.screenshot_sound_toggle)
        layout.addWidget(screenshot_group)

        # QSettings holds nonsensitive preferences ONLY; never vault credentials.
        self.shortcut_editors = {}
        self.shortcut_values = {}
        self.shortcut_objects = {}
        shortcut_group = QGroupBox("Only when ClipMint is focused")
        shortcut_layout = QVBoxLayout(shortcut_group)
        shortcut_note = QLabel(
            "These shortcuts only work in the ClipMint window. They do not "
            "override Firefox or Cinnamon shortcuts."
        )
        shortcut_note.setWordWrap(True)
        shortcut_layout.addWidget(shortcut_note)
        for key, title, default in SHORTCUT_SPECS:
            row = QHBoxLayout()
            label = QLabel(title)
            label.setMinimumWidth(190)
            row.addWidget(label, 1)
            edit = QKeySequenceEdit()
            edit.setToolTip("Click here and press the desired keyboard combination")
            raw = self.settings.value(f"shortcuts/{key}", default)
            sequence = QKeySequence(str(raw) if raw is not None else "")
            canonical = sequence.toString(QKeySequence.SequenceFormat.PortableText)
            self.shortcut_values[key] = canonical
            edit.setKeySequence(sequence)
            edit.keySequenceChanged.connect(
                lambda sequence, action=key: self.change_shortcut(action, sequence)
            )
            self.shortcut_editors[key] = edit
            row.addWidget(edit, 2)
            reset = QPushButton("Reset")
            reset.setToolTip(f"Restore {default}")
            reset.clicked.connect(
                lambda _checked=False, action=key, original=default:
                    self.change_shortcut(action, QKeySequence(original))
            )
            row.addWidget(reset)
            disable = QPushButton("Disable")
            disable.clicked.connect(
                lambda _checked=False, action=key:
                    self.change_shortcut(action, QKeySequence())
            )
            row.addWidget(disable)
            shortcut_layout.addLayout(row)
        local_layout.addWidget(shortcut_group)
        layout.addWidget(QLabel(
            "Vault entries are separately encrypted. Clipboard history needs "
            "the optional secure-history migration above."
        ))
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.pages.addWidget(scroll)

    def set_clip_labels_visible(self, enabled: bool):
        """Display-only preference; never rewrite clipboard history rows."""
        self.settings.setValue("history/show_clip_labels", bool(enabled))
        self.refresh()

    def set_history_storage_limit(self, _index):
        mb = int(self.history_storage_limit.currentData() or 0)
        old_mb = int(self.settings.value("history/max_total_mb", 0, type=int))
        if mb == old_mb:
            return
        if mb:
            answer = QMessageBox.question(
                self, "Apply history storage limit?",
                f"Limit clipboard history payloads to {mb} MB?\n"
                "If current storage exceeds that, this will permanently "
                "remove the oldest UNPINNED history entries now. "
                "Pinned entries will always survive.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.history_storage_limit.blockSignals(True)
                self.history_storage_limit.setCurrentIndex(
                    max(0, self.history_storage_limit.findData(old_mb))
                )
                self.history_storage_limit.blockSignals(False)
                return
        self.store.max_total_bytes = mb * 1024 * 1024 if mb else None
        removed = self.store.prune_storage_bytes()
        self.settings.setValue("history/max_total_mb", mb)
        self.refresh()
        self.statusBar().showMessage(
            f"Storage limit {'off' if not mb else str(mb) + ' MB'}; "
            f"{removed} unpinned clips pruned", 7500,
        )

    def save_ocr_language(self):
        value = self.ocr_language_editor.text().strip().lower()
        try:
            validate_language(value)
        except ValueError as exc:
            self.statusBar().showMessage(str(exc), 6000)
            self.ocr_language_editor.setText(
                str(self.settings.value("ocr/language", "eng"))
            )
            return
        self.settings.setValue("ocr/language", value)
        self.ocr_language_editor.setText(value)

    def install_shortcuts(self):
        callbacks = {
            "search": lambda: (self.open_section(0), self.search.setFocus()),
            "screenshot": self.choose_screenshot,
            "record": self.choose_recording,
            "copy": self.copy_selected,
            "monitor": self.toggle_monitoring,
        }
        occupied = set()
        for key, _title, default in SHORTCUT_SPECS:
            value = self.shortcut_values[key]
            if value and value in occupied:
                # Invalid duplicate values may have been manually written to
                # QSettings. Fail closed rather than running two actions.
                value = default if default not in occupied else ""
                self.shortcut_values[key] = value
                self.settings.setValue(f"shortcuts/{key}", value)
                self._show_shortcut_value(key)
            occupied.add(value) if value else None
            shortcut = QShortcut(QKeySequence(value), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.setEnabled(bool(value))
            shortcut.activated.connect(callbacks[key])
            self.shortcut_objects[key] = shortcut

    def _show_shortcut_value(self, key: str):
        editor = self.shortcut_editors[key]
        editor.blockSignals(True)
        editor.setKeySequence(QKeySequence(self.shortcut_values[key]))
        editor.blockSignals(False)

    def change_shortcut(self, key: str, sequence: QKeySequence) -> bool:
        """Save a user-selected shortcut, or reject a collision atomically."""
        if key not in self.shortcut_values:
            return False
        new_value = sequence.toString(QKeySequence.SequenceFormat.PortableText)
        for other_key, other_value in self.shortcut_values.items():
            if other_key != key and new_value and other_value == new_value:
                self._show_shortcut_value(key)
                self.statusBar().showMessage(
                    f"Shortcut already used by {other_key}. Choose a different key.",
                    5000,
                )
                return False
        self.shortcut_values[key] = new_value
        self.shortcut_objects[key].setKey(QKeySequence(new_value))
        self.shortcut_objects[key].setEnabled(bool(new_value))
        self.settings.setValue(f"shortcuts/{key}", new_value)
        self._show_shortcut_value(key)
        self.statusBar().showMessage(
            f"Shortcut {'disabled' if not new_value else 'saved'}: {key}", 2500
        )
        return True

    def view_bin(self) -> str | None:
        """An optional secondary source selector, not a top history tab."""
        name = self.bin_filter.currentData()
        return name if isinstance(name, str) and name in self.store.bins() else None

    def active_bin(self) -> str:
        """Writable target for unmatched clips; filter tabs never choose it."""
        return self.view_bin() or "Work"

    def new_bin(self):
        name, ok = QInputDialog.getText(self, "New collection", "Collection name:")
        if not ok or not name.strip():
            return
        try:
            self.store.add_bin(name.strip())
        except (ValueError, OSError, Exception) as exc:
            self.error("Collection", str(exc))
            return
        self.bin_filter.addItem(name.strip(), name.strip())
        self.bin_filter.setCurrentIndex(self.bin_filter.count() - 1)

    def open_section(self, index: int):
        self.pages.setCurrentIndex(index)
        self.preview_panel.setVisible(index == 0)
        for i, button in enumerate(self.nav_buttons.values()):
            button.setChecked(index == i)
        if index == 1:
            self.refresh_library("Screenshots")
        elif index == 2:
            self.refresh_library("Recordings")
        elif index == 0:
            self.refresh()

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

    def open_saved_file(self, item):
        target = Path(item.data(Qt.ItemDataRole.UserRole))
        if target.is_file():
            self.open_path(target)

    def set_login_startup_enabled(self, enabled: bool) -> None:
        try:
            set_login_startup(enabled)
        except (AutostartError, OSError) as exc:
            self.login_startup_toggle.blockSignals(True)
            self.login_startup_toggle.setChecked(login_startup_enabled())
            self.login_startup_toggle.blockSignals(False)
            self.error("Start at login", str(exc))

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
        menu.addAction("Quick search popup").triggered.connect(self.toggle_quick_popup)
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
        self.tray.messageClicked.connect(self.tray_notification_clicked)
        self.tray.show()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger and self.recorder_window is None:
            self.show_window()

    def show_window(self):
        if not self.isVisible():
            # Last-chance recovery if the desktop skipped a clipboard signal
            # while the archive was hidden. This can only retrieve the current
            # item, not every intermediate copy made while ClipMint was quit.
            self.poll_hidden_clipboard()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def tray_notification_clicked(self):
        if self._last_tray_notification == "screenshot":
            self.edit_last_screenshot()

    def inform(self, title: str, message: str):
        self._last_tray_notification = None
        self.statusBar().showMessage(f"{title}: {message}", 7000)
        if self.tray is not None:
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

    def error(self, title: str, message: str):
        self.statusBar().showMessage(message, 10000)
        QMessageBox.warning(self.recorder_window or self, title, message)

    def _clipboard_generation_changed(self):
        """Track *all* X11 clipboard writes, including Vault and concealed data."""
        self._sensitive_clipboard_token += 1

    def poll_hidden_clipboard(self):
        """Recover the latest plain-text copy when X11 omits dataChanged.

        Paused/locked monitoring must never capture a clipboard value later
        when the user resumes. No clipboard contents or source titles are
        retained beyond the in-memory digest.
        """
        if self._closing or getattr(self.store, "closed", False):
            return
        if self.isVisible():
            return
        data = QApplication.clipboard().mimeData()
        changed = self._hidden_text_probe.observe(data)
        if changed and self.monitoring and not self.history_security_error:
            self.clipboard_changed()

    def clipboard_changed(self):
        # Clear our own-write expectation on every event, even while history
        # is paused; never carry a stale skip across Pause/Resume.
        data = QApplication.clipboard().mimeData()
        self._hidden_text_probe.observe(data)
        if self._own_clipboard_guard.consume(data):
            return
        if (not self.monitoring or self._closing
                or getattr(self.store, "closed", False) or data is None):
            return
        if is_concealed(data):
            self._privacy_skipped += 1
            self.statusBar().showMessage("Concealed clipboard item excluded")
            return
        if (data.hasText() and self._vault_clipboard_text is not None
                and data.text() == self._vault_clipboard_text):
            return
        if blocked_foreground(str(self.settings.value(
                "privacy/blocked_foreground", ", ".join(DEFAULT_BLOCKED)
        ))):
            self._privacy_skipped += 1
            return
        png = None
        if data.hasImage():
            picture = QApplication.clipboard().image()
            if not picture.isNull():
                buffer_bytes = QByteArray()
                buffer = QBuffer(buffer_bytes)
                if buffer.open(QIODevice.OpenModeFlag.WriteOnly):
                    saved = picture.save(buffer, "PNG")
                    buffer.close()
                    if saved:
                        png = bytes(buffer_bytes)
        entry = from_mime(data, png=png)
        if entry is None:
            # Preserve a generic privacy notice. Expire plaintext secrets
            # only when the clipboard still contains the very same string.
            if data.hasText() and sensitive_text(data.text()):
                original = data.text()
                token = self._sensitive_clipboard_token
                QTimer.singleShot(
                    30000,
                    lambda: self.expire_sensitive_clipboard(token, original),
                )
                self.statusBar().showMessage(
                    "Sensitive clipboard content not saved · clears after "
                    "30 seconds if unchanged", 5500,
                )
            elif is_concealed(data):
                self.statusBar().showMessage(
                    "Sensitive clipboard content detected · not saved to history", 6000
                )
            return
        current_bin = self.active_bin()
        full_text = (entry.content.decode("utf-8", "replace")
                     if entry.kind == "text" else entry.preview)
        target = self.autosort_destination(
            entry.kind, full_text, current_bin, formats=entry.formats
        )
        if target is None:
            self.statusBar().showMessage("Clip excluded by Autosort rule", 4000)
            return
        title = entry.preview
        if entry.kind == "image" and png:
            image = QImage.fromData(png, "PNG")
            title = f"Image {image.width()} × {image.height()}"
        saved_id = self.store.add(
            entry.kind, entry.content, title, target, formats=entry.formats
        )
        if saved_id is not None and self.autosort_enabled:
            category = classify_smart(entry.kind, full_text, entry.formats)
            if category:
                tag = "type_" + category.replace("-", "_")
                existing = self.store.tags(saved_id)
                if tag not in existing and len(existing) < 15:
                    self.store.set_tags(saved_id, [*existing, tag])
        self.refresh()
        if saved_id is not None and self.view_bin() is not None and target != self.view_bin():
            self.statusBar().showMessage(
                f"Clip saved in {target}. Choose All collections to see it.",
                6500,
            )

    def expire_sensitive_clipboard(self, token: int, expected: str) -> None:
        """Never clear unrelated clipboard content copied in the meantime."""
        if token != self._sensitive_clipboard_token:
            return
        clipboard = QApplication.clipboard()
        if clipboard.text() == expected:
            clipboard.clear()

    def _schedule_history_search(self, *_args):
        self._history_search_timer.start()

    def screenshot_context_menu(self, position):
        listing = self.libraries.get("Screenshots")
        if listing is None:
            return
        item = listing.itemAt(position)
        if item is None:
            return
        target = Path(item.data(Qt.ItemDataRole.UserRole))
        menu = QMenu(self)
        ocr = menu.addAction("OCR · Extract text")
        edit = menu.addAction("Open in image editor")
        choice = menu.exec(listing.viewport().mapToGlobal(position))
        if choice == ocr:
            self.start_ocr_file(target)
        elif choice == edit:
            self._last_screenshot_path = target
            self.edit_last_screenshot()

    def ocr_history_clip(self, clip_id: int):
        value = self.store.get(clip_id)
        if value is not None and value[0] == "image":
            self.start_ocr(value[1])

    def ocr_last_screenshot(self):
        if self._last_screenshot_path is not None:
            self.dismiss_screenshot_notice()
            self.start_ocr_file(self._last_screenshot_path)

    def start_ocr_file(self, path: Path):
        try:
            if (not path.is_file() or path.suffix.lower() != ".png"
                    or path.stat().st_size > 16 * 1024 * 1024):
                raise ValueError("Choose a PNG screenshot smaller than 16 MB")
            self.start_ocr(path.read_bytes())
        except (OSError, ValueError) as exc:
            self.error("OCR", str(exc))

    def start_ocr(self, png: bytes):
        if not png or len(png) > 16 * 1024 * 1024:
            self.error("OCR", "Choose a PNG image smaller than 16 MB")
            return
        try:
            language = validate_language(str(
                self.settings.value("ocr/language", "eng")
            ))
            worker = OcrWorker(png, self, language=language)
        except ValueError as exc:
            self.error("OCR", str(exc))
            return
        self._ocr_workers.add(worker)
        worker.recognized.connect(self.ocr_recognized)
        worker.failed.connect(lambda message: self.error("OCR", message))
        worker.finished.connect(lambda: self._ocr_workers.discard(worker))
        self.statusBar().showMessage("OCR: extracting text locally…", 6000)
        worker.start()

    def ocr_recognized(self, text: str):
        if not text.strip():
            self.inform("OCR", "No readable text detected")
            return
        self._own_clipboard_guard.note_text(text)
        QApplication.clipboard().setText(text)
        if (not sensitive_text(text) and not looks_sensitive(text)
                and self.monitoring and not self.history_security_error):
            data = text.encode("utf-8")
            self.store.add("text", data, " ".join(text.split())[:550],
                           self.active_bin(),
                           formats={"text/plain;charset=utf-8": data})
            self.refresh()
            self.inform("OCR complete", "Text copied and saved to clipboard history")
        else:
            self.inform("OCR complete", "Text copied; potential secrets excluded from history")

    def copy_selected(self):
        item = self.history.currentItem()
        if item is not None:
            self.copy_clip(item)

    def copy_clip(self, item):
        value = self.store.get(item.data(Qt.ItemDataRole.UserRole))
        if value is None:
            return
        kind, contents = value
        self._own_clipboard_guard.note_entry(kind, contents)
        QApplication.clipboard().setMimeData(
            mime_from_entry(kind, contents,
                            self.store.get_formats(item.data(Qt.ItemDataRole.UserRole)))
        )
        self.store.refresh_temporary_copy_time(
            item.data(Qt.ItemDataRole.UserRole)
        )
        self.inform("Copied", "Saved snippet copied to the system clipboard")

    def register_cinnamon_hotkey(self):
        sequence = self.global_popup_hotkey.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText
        )
        if not sequence:
            self.error("Cinnamon shortcut", "Choose a keyboard shortcut first")
            return
        executable = (shlex.quote(sys.executable)
                      if getattr(sys, "frozen", False) else
                      shlex.quote(sys.executable) + " " +
                      shlex.quote(str(Path(__file__).resolve().parent.parent / "launcher.py")))
        command = executable + " --toggle"
        try:
            accel = install_shortcut(command, sequence)
        except ShortcutSetupError as exc:
            self.error("Cinnamon shortcut", str(exc))
            return
        self.settings.setValue("popup/global_shortcut", sequence)
        self.inform("Cinnamon shortcut", f"Registered {sequence} ({accel})")

    def _clipmint_launcher_command(self, action: str) -> str:
        """Match the installed app launcher; never shell-expand user content."""
        if getattr(sys, "frozen", False):
            # The packaged stdlib launcher forwards commands straight to the
            # running watcher, avoiding a second PyInstaller/Qt startup.
            executable = shlex.quote(str(Path(sys.executable).with_name("ClipMint")))
        else:
            executable = (shlex.quote(sys.executable) + " " +
                          shlex.quote(str(Path(__file__).resolve().parent.parent / "launcher.py")))
        return executable + " " + action

    def register_cinnamon_screenshot_hotkey(self):
        sequence = self.global_screenshot_hotkey.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText
        )
        if not sequence:
            self.error("Cinnamon screenshot shortcut", "Choose a keyboard shortcut first")
            return
        command = self._clipmint_launcher_command("--screenshot-area")
        try:
            accel = install_shortcut(command, sequence, name="ClipMint screenshot area")
        except ShortcutSetupError as exc:
            if "Explicit permission" not in str(exc):
                self.error("Cinnamon screenshot shortcut", str(exc))
                return
            reply = QMessageBox.question(
                self, "Give ClipMint screenshot priority?",
                "Cinnamon already uses this combination for its own screenshot "
                "tool. Give this combination to ClipMint instead?\n\n"
                "Only the conflicting built-in screenshot binding will be "
                "disabled; its other key combinations will be preserved. "
                "The original is saved for restoration. This changes your "
                "desktop shortcut configuration, not ClipMint's window-only keys.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                accel = install_shortcut(
                    command, sequence, name="ClipMint screenshot area",
                    take_over_screenshot=True,
                )
            except ShortcutSetupError as retry:
                self.error("Cinnamon screenshot shortcut", str(retry))
                return
        self.settings.setValue("capture/global_shortcut", sequence)
        self.inform("Cinnamon shortcut", f"ClipMint screenshot registered: {sequence}")

    def restore_cinnamon_screenshot_hotkey(self):
        sequence = str(self.settings.value("capture/global_shortcut", "Ctrl+Shift+S"))
        command = self._clipmint_launcher_command("--screenshot-area")
        reply = QMessageBox.question(
            self, "Restore Cinnamon screenshot shortcut?",
            "Remove ClipMint's registered screenshot key and restore the "
            "previous built-in screenshot assignment from the local backup? "
            "Existing user edits will not be overwritten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            restored = restore_screenshot_takeover(command, sequence)
        except ShortcutSetupError as exc:
            self.error("Cinnamon screenshot restoration", str(exc))
            return
        self.inform("Cinnamon shortcut",
                    "Previous screenshot assignment restored"
                    if restored else "No ClipMint takeover backup found")

    def register_cinnamon_recording_hotkey(self):
        sequence = self.global_record_hotkey.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText
        )
        if not sequence:
            self.error("Cinnamon recording shortcut", "Choose a keyboard shortcut first")
            return
        command = self._clipmint_launcher_command("--record-area")
        try:
            install_shortcut(command, sequence, name="ClipMint record area")
        except ShortcutSetupError as exc:
            self.error("Cinnamon recording shortcut", str(exc))
            return
        self.settings.setValue("capture/global_record_shortcut", sequence)
        self.inform("Cinnamon shortcut", f"ClipMint recorder registered: {sequence}")

    def audit_global_hotkeys(self):
        """Read-only report of who currently owns our configured global keys."""
        configured = (
            ("Screenshot", str(self.settings.value(
                "capture/global_shortcut", "Ctrl+Shift+S"
            )), self._clipmint_launcher_command("--screenshot-area")),
            ("Recording", str(self.settings.value(
                "capture/global_record_shortcut", "Ctrl+Shift+R"
            )), self._clipmint_launcher_command("--record-area")),
            ("Clipboard popup", str(self.settings.value(
                "popup/global_shortcut", "Ctrl+Alt+V"
            )), self._clipmint_launcher_command("--toggle")),
        )
        report = []
        for title, sequence, expected_command in configured:
            try:
                found = shortcut_conflicts(sequence)
            except ShortcutSetupError as exc:
                report.append(f"{title} · {sequence}: cannot inspect ({exc})")
                continue
            ours = [x for x in found if x["source"] == "custom"
                    and x.get("command") == expected_command]
            others = [x for x in found if x not in ours]
            if ours and not others:
                result = "Assigned to ClipMint in Cinnamon"
            elif others:
                result = "Conflict · another Cinnamon shortcut is assigned"
            else:
                result = "Not registered as a Cinnamon global shortcut"
            report.append(f"{title} · {sequence}: {result}")
        QMessageBox.information(
            self, "ClipMint · Cinnamon hotkeys",
            "\n".join(report) +
            "\n\nThis verifies Cinnamon assignments, not whether another "
            "application, extension or external shortcut daemon intercepts "
            "the same key. Confirm by pressing each shortcut outside ClipMint.",
        )

    def toggle_quick_popup(self):
        self.quick_popup.toggle()

    def quick_pick(self, clip_id: int, plain: bool, wid: str | None, klass: str):
        value = self.store.get(clip_id)
        if value is None:
            return
        kind, content = value
        if plain and kind != "text":
            self.inform("Quick paste", "Plain paste works with text clips only")
            return
        if plain:
            value = content.decode("utf-8", "replace")
            self._own_clipboard_guard.note_text(value)
            QApplication.clipboard().setText(value)
        else:
            self._own_clipboard_guard.note_entry(kind, content)
            QApplication.clipboard().setMimeData(
                mime_from_entry(kind, content, self.store.get_formats(clip_id))
            )
        self.store.refresh_temporary_copy_time(clip_id)
        if wid and self.settings.value("popup/auto_paste", True, type=bool):
            QTimer.singleShot(150, lambda: self._paste_to_target(wid, klass))

    def _paste_to_target(self, wid: str, klass: str):
        mode = str(self.settings.value("popup/terminal_mode", "auto"))
        if not paste_to_window(wid, klass, mode):
            self.statusBar().showMessage(
                "Copied; automatic paste unavailable. Paste manually.", 7000
            )

    def backup_clipboard_archive(self):
        """Export a verified snapshot; never overwrite without confirmation."""
        if self.history_security_error:
            self.error(
                "Archive backup unavailable",
                "Encrypted history could not be unlocked; no plaintext "
                "fallback backup will be created.",
            )
            return
        destination, _chosen_filter = QFileDialog.getSaveFileName(
            self, "Back up current clipboard archive",
            str(Path.home() / "clipmint-history-backup.sqlite3"),
            "SQLite archive (*.sqlite3)",
        )
        if not destination:
            return
        target = Path(destination).expanduser()
        overwrite = False
        if target.exists() or target.is_symlink():
            answer = QMessageBox.question(
                self, "Replace an existing backup?",
                "A file already exists at that location. Replace it with "
                "a new verified backup of your current ClipMint archive?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            overwrite = True
        if not self.history_secure:
            answer = QMessageBox.question(
                self, "Plaintext archive backup",
                "This history is currently UNENCRYPTED. The backup will also "
                "contain unencrypted clipboard text and images, protected "
                "only by your account's file permissions. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            backup_archive(self.store.conn, target, overwrite=overwrite)
        except (ArchiveBackupError, FileExistsError, OSError) as exc:
            self.error("Archive backup", str(exc))
            return
        self.inform(
            "Archive backup complete",
            "Encrypted archive saved; the desktop keyring key is NOT included."
            if self.history_secure else
            "Archive saved with owner-only permissions (0600). "
            "The contents are NOT encrypted.",
        )

    def remove_old_plaintext_history(self):
        """Only delete legacy data after read-back, user confirmation and recheck."""
        if not self.history_secure or not isinstance(self.store, EncryptedClipStore):
            self.error("Encrypted history", "Unlock encrypted history first")
            return
        try:
            old_path, checked = verify_legacy_history(self.store)
        except (HistorySecurityError, OSError, ValueError) as exc:
            self.error("Legacy history", str(exc))
            return
        answer = QMessageBox.question(
            self, "Remove verified plaintext history?",
            f"Verified {checked} original clipboard entries in the encrypted archive.\n\n"
            "Permanently remove the old plaintext SQLite database and its WAL "
            "sidecars? This cannot be undone. Any separate backups, disk "
            "snapshots or SSD remnant data may still contain plaintext; this "
            "is NOT a forensic secure erase. Make sure your encrypted archive "
            "and keyring key are backed up first.\n\n"
            f"File: {old_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = remove_verified_legacy_history(self.store)
        except (HistorySecurityError, OSError, ValueError) as exc:
            self.error("Legacy history", str(exc))
            return
        self.remove_legacy_button.setEnabled(False)
        self.inform("Legacy history removed",
                    f"Removed old plaintext database after verifying {removed} entries")

    def enable_encrypted_history(self):
        if self.history_secure:
            return
        confirmation = QMessageBox.question(
            self, "Encrypt clipboard history",
            "This creates a separate encrypted SQLite database using your unlocked "
            "desktop Secret Service keyring. The original plaintext database is "
            "preserved for recovery. After verification, you may optionally remove "
            "the old plaintext database in Settings. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        try:
            key = key_from_secret_service(create=True)
            secure = EncryptedClipStore.migrate_legacy(
                self.store, secure_path(), key
            )
        except (HistorySecurityError, OSError, ValueError) as exc:
            self.error("Encrypted history", str(exc))
            return
        secure.max_total_bytes = self.store.max_total_bytes
        self.store.close()
        self.store = secure
        self.quick_popup.store = secure
        self.history_secure = True
        self.history_security_error = ""
        # Enabling encrypted history also resumes monitoring. Just like
        # Resume, baseline the current clipboard first so paused text cannot
        # leak into the new encrypted archive on the next hidden poll.
        self._hidden_text_probe.observe(QApplication.clipboard().mimeData())
        self.monitoring = True
        self.settings.setValue("privacy/history_secure", True)
        self.secure_history_button.setText("Encrypted history active")
        self.secure_history_button.setEnabled(False)
        self.remove_legacy_button.setEnabled(True)
        self.refresh()
        self.inform(
            "History encrypted",
            "New captures are encrypted. The old plaintext history still exists."
        )

    def update_temporary_expiry_schedule(self):
        enabled = (not self.history_security_error and
                   self.settings.value("temporary/expire_24h", False, type=bool))
        if enabled:
            self._temporary_expiry_timer.start()
        else:
            self._temporary_expiry_timer.stop()

    def set_temporary_expiry_enabled(self, enabled: bool):
        if enabled:
            confirmation = QMessageBox.question(
                self, "Enable Temporary expiry?",
                "Automatically delete unpinned Temporary items 24 hours after "
                "they were saved? Any already older than 24 hours will be "
                "removed immediately. Pinned items and other collections "
                "will remain untouched.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirmation != QMessageBox.StandardButton.Yes:
                self.temporary_expiry_toggle.blockSignals(True)
                self.temporary_expiry_toggle.setChecked(False)
                self.temporary_expiry_toggle.blockSignals(False)
                return
        self.settings.setValue("temporary/expire_24h", enabled)
        self.update_temporary_expiry_schedule()
        if enabled:
            self.expire_temporary_if_enabled()

    def invalidate_removed_clip_references(self, removed_ids: list[int]):
        """Never let queued/popup IDs outlive deleted SQLite history rows."""
        if not removed_ids:
            return
        self.paste_queue.discard_ids(removed_ids)
        self._refresh_queue_button()
        if self.quick_popup.isVisible():
            self.quick_popup.refresh()
        else:
            self.quick_popup.items.clear()

    def expire_temporary_if_enabled(self):
        if (self.history_security_error or not self.settings.value(
            "temporary/expire_24h", False, type=bool
        )):
            return
        removed_ids: list[int] = []
        try:
            removed = self.store.expire_temporary_unpinned(
                deleted_ids=removed_ids
            )
        except (sqlite3.DatabaseError, OSError) as exc:
            # Deletions may already be committed even if SQLite maintenance
            # fails. Never let a failure preserve stale queued clipboard IDs.
            self.invalidate_removed_clip_references(removed_ids)
            if removed_ids:
                self.refresh()
            self._temporary_expiry_timer.stop()
            self.error("Temporary expiry", str(exc))
            return
        if removed:
            self.invalidate_removed_clip_references(removed_ids)
            self.refresh()
            self.statusBar().showMessage(
                f"Temporary: {removed} expired unpinned clip(s) removed", 5000
            )

    def clear_temporary_on_normal_exit(self):
        """Never run for crashes, updates, or close-to-tray actions."""
        if self._temporary_exit_cleaned:
            return
        if self.history_security_error or not self.settings.value(
            "temporary/clear_on_quit", False, type=bool
        ):
            return
        try:
            self.store.clear_temporary_unpinned()
        except (sqlite3.DatabaseError, OSError) as exc:
            QMessageBox.warning(
                self, "Temporary cleanup was not completed", str(exc)
            )
            return
        self._temporary_exit_cleaned = True

    def toggle_monitoring(self):
        if self.history_security_error:
            self.error("Clipboard privacy", "Unlock the desktop keyring and restart ClipMint")
            return
        if not self.monitoring:
            # A pause may end before the next hidden poll. Baseline the
            # CURRENT system clipboard now, so nothing copied during pause
            # can be ingested merely because monitoring was resumed.
            self._hidden_text_probe.observe(QApplication.clipboard().mimeData())
        self.monitoring = not self.monitoring
        self.pause_button.setText("Pause monitoring" if self.monitoring else "Resume monitoring")
        self.refresh()
        self.inform("Clipboard monitoring", "Enabled" if self.monitoring else "Paused")

    def select_area(self, purpose: str):
        if self.selector is not None or self.recorder_window is not None:
            return
        if purpose == "video" and self.recorder.process is not None:
            self.inform("Recording", "Finish the current recording first")
            return
        # Only return to ClipMint if the user was working in its foreground
        # window. Global Cinnamon grabs must not summon it over Firefox.
        self._capture_restore_main = self.isVisible() and self.isActiveWindow()
        # The main window AND the screenshot notice can appear in a capture
        # unless the compositor has had time to hide a previously visible UI.
        had_visible_window = self.isVisible() or (
            self.screenshot_notice is not None
            and self.screenshot_notice.isVisible()
        )
        if self.screenshot_notice is not None:
            self.screenshot_notice.hide()
        # An already hidden UI needs no compositor settling delay.
        self.hide()
        QTimer.singleShot(
            250 if had_visible_window else 0,
            lambda: self.begin_selection(purpose),
        )

    def begin_selection(self, purpose):
        try:
            self.selector = AreaSelector(purpose)
        except Exception as exc:
            if self._capture_restore_main:
                self.show_window()
            self._capture_restore_main = False
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
        if self._capture_restore_main:
            self.show_window()
        self._capture_restore_main = False

    def choose_screenshot(self):
        self.select_area("image")

    def screenshot_full(self):
        if self.selector is not None or self.recorder.active:
            return
        self._capture_restore_main = self.isVisible() and self.isActiveWindow()
        if self.screenshot_notice is not None:
            self.screenshot_notice.hide()
        self.hide()
        QTimer.singleShot(350, self.finish_full_screenshot)

    def finish_full_screenshot(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            if self._capture_restore_main:
                self.show_window()
            self._capture_restore_main = False
            self.error("Screenshot", "No screen detected")
            return
        self.save_screenshot(None, screen.grabWindow(0))

    def save_screenshot(self, _rect, pixmap):
        QTimer.singleShot(0, self.clear_selection)
        path = screenshots_dir() / stamped_filename("screenshot", "png")
        if pixmap.isNull() or not pixmap.save(str(path), "PNG"):
            if self._capture_restore_main:
                self.show_window()
            self._capture_restore_main = False
            self.error("Screenshot", "Could not save screenshot")
            return
        # Make the pixels immediately pasteable into Firefox / another app.
        # Clipboard history may also record the image as an ordinary clip.
        # Defensive: successful capture is always a background operation.
        # Keep the archive hidden even when a future caller bypasses the
        # ordinary region-selection path that already hides the window.
        self.hide()
        QApplication.clipboard().setImage(pixmap.toImage())
        # Successful screenshots must NEVER summon the main app, even when
        # launched from a button in the previously active ClipMint window.
        # The selection widget was closed and the main app was hidden before
        # sampling the screen. User actions live in the small independent
        # screenshot notice; Ctrl+V works without choosing one.
        self._capture_restore_main = False
        self.notify_screenshot_captured(path)
        # Update the archive without switching to or raising the main window.
        self.refresh_library("Screenshots", select_path=path)

    def notify_screenshot_captured(self, path: Path):
        """Notify only after a PNG was saved successfully to disk."""
        self._last_screenshot_path = Path(path)
        self._screenshot_notice_token += 1
        token = self._screenshot_notice_token
        self.statusBar().showMessage(f"Screenshot captured: {path}", 8000)
        if self.screenshot_notice is not None:
            self.screenshot_notice.present()
            QTimer.singleShot(
                10000, lambda: self.dismiss_screenshot_notice(token)
            )
        # Do not duplicate the two-action popup with a tray balloon.
        # The standard Cinnamon shutter event is best-effort, never blocking.
        if self.settings.value("capture/sound_enabled", True, type=bool):
            play_capture_sound()

    def dismiss_screenshot_notice(self, token=None):
        if type(token) is int and token != self._screenshot_notice_token:
            return
        if self.screenshot_notice is not None:
            self.screenshot_notice.hide()

    def edit_last_screenshot(self, *_args):
        """A notification click must never create a new screenshot."""
        path = self._last_screenshot_path
        if path is None:
            return
        preference = str(self.settings.value("capture/editor", "auto"))
        try:
            application, editor = open_image_editor(path, preference)
        except (OSError, ValueError) as exc:
            self.error(
                "Screenshot editor",
                f"Could not open the captured PNG: {exc}. "
                "Choose an installed editor in Settings.",
            )
            return
        self.dismiss_screenshot_notice()
        if editor:
            self.statusBar().showMessage(
                f"Opening screenshot in {application}", 5000
            )
        else:
            self.statusBar().showMessage(
                "Opening screenshot with the system image application; "
                "it may be a viewer. Select an editor in Settings.", 8000
            )

    def open_path(self, path: Path):
        try:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError as exc:
            self.error("Open", str(exc))

    def open_folder(self, folder: Path):
        self.open_path(folder)

    def closeEvent(self, event):
        self.lock_vault()
        if self._closing:
            event.accept()
            return
        # The X button closes the interface, not the clipboard watcher.
        # System tray availability is not reliable on every Cinnamon panel.
        # The single-instance socket makes the hidden window reachable again
        # through the normal launcher, including on desktops without a tray.
        self.hide()
        event.ignore()

    def quit_app(self):
        if self.recorder.process is not None:
            self.error("Recording active", "Finish recording before quitting")
            return
        if self.recorder_window is not None:
            self.recorder_window.hide()
            self.recorder_window.deleteLater()
            self.recorder_window = None
        self._closing = True
        self._auto_update_timer.stop()
        self._hidden_clipboard_timer.stop()
        self.lock_vault()
        self.clear_temporary_on_normal_exit()
        self.store.close()
        if self.tray is not None:
            self.tray.hide()
        QApplication.quit()


def main():
    if sys.platform != "linux":
        raise SystemExit("ClipMint currently supports Linux only")
    arguments = sys.argv[1:]
    capture = ("screenshot-area" if "--screenshot-area" in arguments else
               "record-area" if "--record-area" in arguments else None)
    hidden = "--hidden" in arguments and not (
        capture or "--toggle" in arguments or "--quit" in arguments
    )
    command = (capture if capture else
               "toggle" if "--toggle" in arguments else
               "quit" if "--quit" in arguments else
               "ping" if hidden else "show")
    # Every invocation first signals an existing instance. The running daemon
    # owns the clipboard; --toggle never starts a second clipboard watcher.
    app = QApplication([sys.argv[0]])
    app.setApplicationName("ClipMint")
    # The Qt event loop and clipboard signals must remain alive after *all*
    # windows are hidden. Only explicit Quit/--quit ends the watcher.
    app.setQuitOnLastWindowClosed(False)
    if send_command(command):
        return
    if command == "quit":
        return
    if os.environ.get("XDG_SESSION_TYPE", "x11").lower() != "x11":
        QMessageBox.warning(None, "X11 required",
                            "ClipMint currently requires an X11 session (e.g. Cinnamon X11).")
        raise SystemExit(1)
    window = ClipMintWindow()
    def on_command(action):
        if action == "toggle":
            window.toggle_quick_popup()
        elif action == "show":
            window.show_window()
        elif action == "screenshot-area":
            QTimer.singleShot(0, window.choose_screenshot)
        elif action == "record-area":
            QTimer.singleShot(0, lambda: window.choose_recording("MP4"))
        elif action == "quit":
            window.quit_app()
    try:
        window._instance_server = InstanceServer(
            on_command, window, occupied_command="ping" if hidden else "show"
        )
    except RuntimeError as exc:
        QMessageBox.warning(None, "ClipMint", str(exc))
        return
    if command == "toggle":
        QTimer.singleShot(150, window.toggle_quick_popup)
    elif command == "screenshot-area":
        # A cold-start global screenshot key must not reveal the main window.
        QTimer.singleShot(0, window.choose_screenshot)
    elif command == "record-area":
        window.show()
        QTimer.singleShot(150, lambda: window.choose_recording("MP4"))
    elif hidden:
        # Login startup runs headlessly regardless of the desktop's tray
        # support. Reopen through the app launcher (single-instance 'show').
        pass
    else:
        window.show()
    raise SystemExit(app.exec())
