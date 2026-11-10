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
from .library_controller import LibraryControllerMixin, ImagePreviewLabel
from .hotkey_popup_controller import HotkeyPopupControllerMixin
from .clipboard_monitor import ClipboardMonitorMixin
from .history_maintenance_controller import HistoryMaintenanceMixin
from .history_security_controller import HistorySecurityControllerMixin
from .screenshot_capture_controller import ScreenshotCaptureControllerMixin
from .app_lifecycle_controller import AppLifecycleMixin
from .ocr_controller import OcrControllerMixin
from .settings_controller import SettingsControllerMixin, SHORTCUT_SPECS, WheelSafeHistoryLimitComboBox
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


class ClipMintWindow(OcrControllerMixin, AppLifecycleMixin, ScreenshotCaptureControllerMixin, HistorySecurityControllerMixin, HistoryMaintenanceMixin, ClipboardMonitorMixin, HotkeyPopupControllerMixin, LibraryControllerMixin, SettingsControllerMixin, HistoryControllerMixin, UpdateControllerMixin, AutosortControllerMixin, VaultControllerMixin, RecordingControllerMixin, QMainWindow):
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
        self._initialize_encrypted_history()
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

    def _schedule_history_search(self, *_args):
        self._history_search_timer.start()

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
