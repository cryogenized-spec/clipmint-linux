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
    QKeySequenceEdit, QGroupBox, QCheckBox, QDialogButtonBox,
    QFormLayout, QAbstractItemView, QFileDialog, QScrollArea, QListView,
)

from .branding import ChromaticWordmark, register_display_font
from .manga import CrimsonMaidPortrait
from .crimson_ui import build_crimson_ui, relative_time, label_type
from .capture import AreaSelector, RegionRecorder, recordings_dir, screenshots_dir, stamped_filename
from .recording_ui import RecorderWindow, SaveClipDialog
from .store import ClipStore, classify, looks_sensitive
from .autosort import RULE_TYPES, NEVER_CAPTURE, validate_rule, route_clip
from .smart_types import (SMART_TYPES, TYPE_BY_KEY, DEFAULT_BINS as SMART_BINS,
                          classify_smart, default_smart_rules)
from .vault import Vault, VaultError
from .screenshot_editor import installed_editors, resolve_editor, open_image_editor
from .screenshot_notice import ScreenshotNotice
from .screenshot_gallery import read_screenshot, screenshot_thumbnail_icon, PREVIEW_SIZE
from .clipboard_formats import from_mime, is_concealed, sensitive_text, mime_from_entry
from .foreground_privacy import blocked_foreground, DEFAULT_BLOCKED
from .ocr import OcrWorker
from .quick_popup import QuickPopup, paste_to_window
from .productivity import PasteQueue
from .organizer_ui import TemplatesDialog, TransformDialog
from .single_instance import InstanceServer, send_command
from .cinnamon_hotkey import (install_shortcut, restore_screenshot_takeover,
                              shortcut_conflicts, ShortcutSetupError)
from .secure_history import (EncryptedClipStore, HistorySecurityError,
                             key_from_secret_service, secure_path)
from .archive_backup import backup_archive, ArchiveBackupError
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


class ClipMintWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClipMint · Clipboard & Capture")
        self.brand_family = register_display_font()
        self.resize(1300, 870)
        self.setMinimumSize(850, 600)
        self.store = ClipStore()
        self.settings = QSettings("ClipMint", "ClipMint")
        self._temporary_exit_cleaned = False
        self._temporary_expiry_timer = QTimer(self)
        self._temporary_expiry_timer.setInterval(5 * 60 * 1000)
        self._temporary_expiry_timer.timeout.connect(self.expire_temporary_if_enabled)
        self.history_secure = False
        self.history_security_error = ""
        if self.settings.value("privacy/history_secure", False, type=bool):
            try:
                if not secure_path().is_file():
                    raise HistorySecurityError("Encrypted history file not found")
                key = key_from_secret_service(create=False)
                encrypted = EncryptedClipStore(secure_path(), key)
                self.store.close()
                self.store = encrypted
                self.history_secure = True
            except (HistorySecurityError, OSError) as exc:
                self.history_security_error = str(exc)
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
        self.monitoring = not bool(self.history_security_error)
        self.selector: AreaSelector | None = None
        self.recorder_window: RecorderWindow | None = None
        self.capture_rect = None
        self.capture_format = "MP4"
        self._privacy_skipped = 0
        self._closing = False
        self._ignore_next_clipboard_change = False
        self._last_screenshot_path = None
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
            self.history_security_error or
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
        QTimer.singleShot(400, self.clipboard_changed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "manga_dock"):
            self._update_manga_visibility()
        if getattr(self, "screenshot_notice", None) is not None:
            self.screenshot_notice.position_inside_window()

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
        self.category.addItems(["All", "Text", "URLs", "Phone numbers", "Images", "Files"])
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

    def refresh_vault(self):
        configured, unlocked = self.vault.configured, self.vault.unlocked
        self.vault_status.setText(
            "● UNLOCKED · decrypted in memory temporarily" if unlocked
            else "● LOCKED · passphrase required" if configured
            else "● NOT CONFIGURED · create a private vault"
        )
        self.vault_items.clear()
        if unlocked:
            for entry in self.vault.list_entries():
                item = QListWidgetItem(
                    f"{entry['kind'].upper()}  ·  {entry['name']}"
                )
                item.setData(Qt.ItemDataRole.UserRole, entry["id"])
                self.vault_items.addItem(item)
        for name, button in self.vault_actions.items():
            button.setEnabled({
                "create": not configured,
                "restore": not configured,
                "unlock": configured and not unlocked,
                "lock": unlocked,
                "backup": configured,
                "wipe": configured,
                "add": unlocked, "reveal": unlocked,
                "copy": unlocked, "remove": unlocked,
                "rotate": unlocked,
            }[name])

    def touch_vault(self):
        if self.vault.unlocked:
            self._vault_lock_timer.start(5 * 60 * 1000)

    def vault_password_prompt(self, title: str, message: str) -> str | None:
        value, ok = QInputDialog.getText(
            self, title, message, QLineEdit.EchoMode.Password
        )
        return value if ok else None

    def create_vault(self):
        password = self.vault_password_prompt(
            "Create encrypted vault", "Choose a passphrase (at least 12 characters):"
        )
        if password is None:
            return
        again = self.vault_password_prompt(
            "Confirm passphrase", "Enter the same passphrase again:"
        )
        if again is None:
            return
        if password != again:
            self.error("Vault", "Passphrases do not match")
            return
        try:
            self.vault.create(password)
            self.refresh_vault()
            self.touch_vault()
            self.inform(
                "Vault created",
                "Keep your passphrase safe. There is no recovery without it."
            )
        except VaultError as exc:
            self.error("Vault", str(exc))

    def unlock_vault(self):
        password = self.vault_password_prompt("Unlock vault", "Vault passphrase:")
        if password is None:
            return
        try:
            self.vault.unlock(password)
            self.refresh_vault()
            self.touch_vault()
        except VaultError as exc:
            self.error("Vault", str(exc))

    def lock_vault(self):
        self._vault_lock_timer.stop()
        self.vault.lock()
        self.refresh_vault()

    def selected_vault_id(self) -> str | None:
        item = self.vault_items.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def add_vault_entry(self):
        if not self.vault.unlocked:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Save encrypted entry")
        fields = QFormLayout(dialog)
        kind = QComboBox()
        kind.addItems(["Secret", "Variable"])
        name = QLineEdit()
        value = QLineEdit()
        value.setEchoMode(QLineEdit.EchoMode.Password)
        value.setPlaceholderText("Stored encrypted; never captured as history")
        kind.currentTextChanged.connect(
            lambda text: value.setEchoMode(
                QLineEdit.EchoMode.Password if text == "Secret"
                else QLineEdit.EchoMode.Normal
            )
        )
        fields.addRow("Type", kind)
        fields.addRow("Name", name)
        fields.addRow("Value", value)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        fields.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.vault.add(name.text(), value.text(), kind.currentText())
            value.clear()
            self.touch_vault()
            self.refresh_vault()
        except VaultError as exc:
            self.error("Vault", str(exc))

    def reveal_vault_value(self):
        entry_id = self.selected_vault_id()
        if entry_id is None or not self.vault.unlocked:
            return
        try:
            value = self.vault.get_value(entry_id)
        except VaultError as exc:
            self.error("Vault", str(exc))
            return
        self.touch_vault()
        dialog = QDialog(self)
        dialog.setWindowTitle("Reveal saved entry")
        form = QFormLayout(dialog)
        field = QLineEdit(value)
        field.setReadOnly(True)
        field.setEchoMode(QLineEdit.EchoMode.Password)
        reveal = QCheckBox("Show value while this dialog is open")
        reveal.toggled.connect(
            lambda checked: field.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        # Copy the full value directly from the unlocked vault, regardless
        # of cursor position, text selection or masked display state.
        copy_button = QPushButton("Copy")
        copy_button.setObjectName("vaultRevealCopy")
        copy_button.setToolTip("Copy the complete value without revealing it")
        copy_button.clicked.connect(
            lambda _checked=False: self.copy_specific_vault_value(
                entry_id, feedback_button=copy_button
            )
        )
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        form.addRow("Value", field)
        form.addRow("", reveal)
        form.addRow("Clipboard", copy_button)
        clipboard_note = QLabel("Clipboard clears after 30 seconds if unchanged.")
        clipboard_note.setObjectName("captureDetails")
        form.addRow("", clipboard_note)
        form.addRow(close)
        dialog.exec()
        field.clear()

    def copy_vault_value(self, *_args):
        """Copy from the main vault list without relying on selected text."""
        entry_id = self.selected_vault_id()
        if entry_id is not None:
            self.copy_specific_vault_value(
                entry_id, feedback_button=self.vault_actions.get("copy")
            )

    def copy_specific_vault_value(
        self, entry_id: str, *, feedback_button: QPushButton | None = None
    ) -> None:
        """Copy the entire decrypted value; never add it to clipboard history."""
        if not self.vault.unlocked:
            return
        try:
            value = self.vault.get_value(entry_id)
        except VaultError as exc:
            self.error("Vault", str(exc))
            return
        self.touch_vault()
        self._vault_clipboard_text = value
        self._vault_clipboard_token += 1
        token = self._vault_clipboard_token
        self._ignore_next_clipboard_change = True
        QApplication.clipboard().setText(value)
        QTimer.singleShot(30000, lambda: self.expire_vault_clipboard(token))

        if feedback_button is not None:
            feedback_button.setText("✓ Copied!")
            feedback_button.setAccessibleName("Copied!")
            # A timer owned by the button can't update a closed dialog.
            timer = getattr(feedback_button, "_clipmint_copy_timer", None)
            if timer is None:
                timer = QTimer(feedback_button)
                timer.setSingleShot(True)
                timer.timeout.connect(
                    lambda: self.reset_vault_copy_feedback(feedback_button)
                )
                feedback_button._clipmint_copy_timer = timer
            timer.start(1800)
        self.statusBar().showMessage("Copied!", 3000)

    @staticmethod
    def reset_vault_copy_feedback(button: QPushButton) -> None:
        button.setText("Copy")
        button.setAccessibleName("Copy full value")

    def expire_vault_clipboard(self, token: int):
        if token != self._vault_clipboard_token:
            return
        value = self._vault_clipboard_text
        if value is not None and QApplication.clipboard().text() == value:
            self._ignore_next_clipboard_change = True
            QApplication.clipboard().clear()
        self._vault_clipboard_text = None

    def remove_vault_entry(self):
        entry_id = self.selected_vault_id()
        if entry_id is None:
            return
        if QMessageBox.question(
            self, "Delete entry",
            "Permanently delete this vault entry?",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.vault.remove(entry_id)
            self.touch_vault()
            self.refresh_vault()
        except VaultError as exc:
            self.error("Vault", str(exc))

    def change_vault_passphrase(self):
        if not self.vault.unlocked:
            return
        old = self.vault_password_prompt("Change passphrase", "Current passphrase:")
        if old is None:
            return
        new = self.vault_password_prompt("Change passphrase", "New passphrase:")
        if new is None:
            return
        confirm = self.vault_password_prompt("Confirm passphrase", "Repeat new passphrase:")
        if confirm is None:
            return
        if new != confirm:
            self.error("Vault", "Passphrases do not match")
            return
        try:
            self.vault.change_passphrase(old, new)
            self.touch_vault()
            self.inform("Vault", "Passphrase updated. Create a fresh encrypted backup.")
        except VaultError as exc:
            self.error("Vault", str(exc))

    def backup_vault(self):
        if not self.vault.configured:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save encrypted vault backup", "clipmint-vault-backup.json",
            "Encrypted vault (*.json *.vault)"
        )
        if not filename:
            return
        try:
            self.vault.encrypted_backup(Path(filename))
            self.inform("Vault backup", "Encrypted backup saved. Retain its passphrase.")
        except VaultError as exc:
            self.error("Vault", str(exc))

    def restore_vault(self):
        if self.vault.configured:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Restore encrypted vault backup", "",
            "Encrypted vault (*.json *.vault)"
        )
        if not filename:
            return
        try:
            self.vault.restore_backup(Path(filename))
            self.refresh_vault()
            self.inform("Vault", "Encrypted backup restored. Unlock with its original passphrase.")
        except VaultError as exc:
            self.error("Vault", str(exc))

    def wipe_vault(self):
        if not self.vault.configured:
            return
        response, ok = QInputDialog.getText(
            self, "Delete encrypted vault",
            "This deletes the local encrypted file. Backups are not deleted. "
            "Type DELETE to confirm:",
        )
        if not ok or response != "DELETE":
            return
        try:
            self._vault_lock_timer.stop()
            self.vault.wipe()
            self.refresh_vault()
            self.inform("Vault deleted", "Local encrypted vault removed.")
        except VaultError as exc:
            self.error("Vault", str(exc))

    def build_autosort_page(self):
        """Native Qt rule editor with editable first-run smart defaults."""
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Autosort · routing rules")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        summary = QLabel(
            "30 editable smart content types are supplied by default and "
            "enabled on a fresh setup. Sensitive types are never stored in "
            "ordinary history. Other clips go into grouped collections; "
            "first matching rule wins. Existing items are not moved."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        first_setup = not self.settings.contains("autosort/rules")
        if first_setup:
            self.settings.setValue(
                "autosort/rules", json.dumps(default_smart_rules())
            )
        if first_setup and not self.settings.contains("autosort/enabled"):
            self.settings.setValue("autosort/enabled", True)
        self.autosort_enabled = self.settings.value(
            "autosort/enabled", first_setup, type=bool
        )
        self.autosort_rules = []
        try:
            saved = json.loads(str(self.settings.value("autosort/rules", "[]")))
            if isinstance(saved, list):
                for candidate in saved[:100]:
                    try:
                        self.autosort_rules.append(
                            validate_rule(candidate, self.store.bins())
                        )
                    except (ValueError, TypeError):
                        pass  # Stale destinations and invalid patterns fail closed.
        except (ValueError, TypeError):
            pass
        self.autosort_switch = QCheckBox("Enable automatic routing for new clips")
        self.autosort_switch.setChecked(self.autosort_enabled)
        self.autosort_switch.toggled.connect(self.toggle_autosort)
        layout.addWidget(self.autosort_switch)
        self.autosort_list = QListWidget()
        self.autosort_list.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove
        )
        self.autosort_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.autosort_list.setToolTip(
            "Drag rows to reorder priority. Uncheck a row to disable that rule."
        )
        self.autosort_list.itemChanged.connect(self.toggle_autosort_rule)
        self.autosort_list.model().rowsMoved.connect(self.autosort_reordered)
        layout.addWidget(self.autosort_list, 1)
        controls = QHBoxLayout()
        for name, callback in (
            ("Add", self.add_autosort_rule),
            ("Edit", self.edit_autosort_rule),
            ("Remove", self.remove_autosort_rule),
            ("Move up", lambda: self.move_autosort_rule(-1)),
            ("Move down", lambda: self.move_autosort_rule(1)),
            ("Restore 30 defaults", self.restore_autosort_defaults),
        ):
            button = QPushButton(name)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)
        test_button = QPushButton("Test selected history clip against these rules")
        test_button.clicked.connect(self.test_autosort)
        layout.addWidget(test_button)
        self.autosort_test_result = QLabel(
            "Pattern matching is local. Credentials detected by the privacy "
            "filter are excluded before any Autosort rule runs."
        )
        self.autosort_test_result.setWordWrap(True)
        layout.addWidget(self.autosort_test_result)
        self.pages.addWidget(page)
        self.refresh_autosort_list()

    def toggle_autosort(self, enabled: bool):
        self.autosort_enabled = enabled
        self.settings.setValue("autosort/enabled", enabled)
        self.statusBar().showMessage(
            "Autosort enabled" if enabled else "Autosort disabled", 3000
        )

    def persist_autosort(self):
        self.settings.setValue("autosort/rules", json.dumps(self.autosort_rules))

    def refresh_autosort_list(self, selected: int = -1):
        self.autosort_list.blockSignals(True)
        self.autosort_list.clear()
        for i, rule in enumerate(self.autosort_rules):
            descriptor = (
                TYPE_BY_KEY[rule["pattern"]].label
                if rule["mode"] == "Smart"
                else f"{rule['mode']}: {rule['pattern']}"
                if rule["mode"] in ("Keyword", "Regex")
                else rule["mode"]
            )
            item = QListWidgetItem(
                f"{i + 1:02d}   {descriptor}   →   {rule['target']}"
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                          | Qt.ItemFlag.ItemIsDragEnabled)
            item.setCheckState(
                Qt.CheckState.Checked if rule["enabled"]
                else Qt.CheckState.Unchecked
            )
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.autosort_list.addItem(item)
        if 0 <= selected < self.autosort_list.count():
            self.autosort_list.setCurrentRow(selected)
        self.autosort_list.blockSignals(False)

    def toggle_autosort_rule(self, item: QListWidgetItem):
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int) and 0 <= index < len(self.autosort_rules):
            self.autosort_rules[index]["enabled"] = (
                item.checkState() == Qt.CheckState.Checked
            )
            self.persist_autosort()

    def autosort_reordered(self, *_args):
        positions = [
            self.autosort_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.autosort_list.count())
        ]
        if sorted(positions) == list(range(len(self.autosort_rules))):
            self.autosort_rules = [self.autosort_rules[i] for i in positions]
            self.persist_autosort()
            self.refresh_autosort_list()

    def edit_autosort_dialog(self, original: dict | None = None) -> dict | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Autosort rule" if original else "Add Autosort rule")
        form = QFormLayout(dialog)
        mode = QComboBox()
        mode.addItems(RULE_TYPES)
        pattern = QLineEdit()
        pattern.setMaxLength(200)
        pattern.setPlaceholderText("Keyword or regular expression")
        smart_choice = QComboBox()
        for smart in SMART_TYPES:
            smart_choice.addItem(smart.label, smart.key)
        destination = QComboBox()
        destination.addItems([*self.store.bins(), NEVER_CAPTURE])
        enabled = QCheckBox("Rule enabled")
        enabled.setChecked(original.get("enabled", True) if original else True)
        form.addRow("Match", mode)
        form.addRow("Keyword / regex", pattern)
        form.addRow("Smart category", smart_choice)
        form.addRow("Then", destination)
        form.addRow("", enabled)
        if original:
            mode.setCurrentText(original["mode"])
            pattern.setText(original["pattern"])
            destination.setCurrentText(original["target"])
            if original["mode"] == "Smart":
                idx = smart_choice.findData(original["pattern"])
                smart_choice.setCurrentIndex(max(0, idx))

        def on_mode_changed(current: str) -> None:
            pattern.setEnabled(current in ("Keyword", "Regex"))
            smart_choice.setEnabled(current == "Smart")

        def on_smart_changed(_index: int) -> None:
            if mode.currentText() == "Smart":
                selected = TYPE_BY_KEY.get(smart_choice.currentData())
                if selected:
                    destination.setCurrentText(selected.bin)

        mode.currentTextChanged.connect(on_mode_changed)
        smart_choice.currentIndexChanged.connect(on_smart_changed)
        on_mode_changed(mode.currentText())
        if original is None and mode.currentText() == "Smart":
            on_smart_changed(smart_choice.currentIndex())
        actions = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        form.addRow(actions)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                return validate_rule({
                    "mode": mode.currentText(),
                    "pattern": (smart_choice.currentData()
                                if mode.currentText() == "Smart"
                                else pattern.text()),
                    "target": destination.currentText(),
                    "enabled": enabled.isChecked(),
                }, self.store.bins())
            except ValueError as exc:
                QMessageBox.warning(dialog, "Invalid Autosort rule", str(exc))
        return None

    def add_autosort_rule(self):
        rule = self.edit_autosort_dialog()
        if rule is not None:
            # A custom rule appended after the broad Plain Text fallback
            # would never match normal prose. Insert just before that fallback.
            next_index = next((
                i for i, item in enumerate(self.autosort_rules)
                if item["mode"] == "Smart" and item["pattern"] == "plain-text"
            ), len(self.autosort_rules))
            self.autosort_rules.insert(next_index, rule)
            self.persist_autosort()
            self.refresh_autosort_list(next_index)

    def edit_autosort_rule(self):
        i = self.autosort_list.currentRow()
        if i < 0:
            return
        replacement = self.edit_autosort_dialog(self.autosort_rules[i])
        if replacement is not None:
            self.autosort_rules[i] = replacement
            self.persist_autosort()
            self.refresh_autosort_list(i)

    def remove_autosort_rule(self):
        i = self.autosort_list.currentRow()
        if i >= 0:
            self.autosort_rules.pop(i)
            self.persist_autosort()
            self.refresh_autosort_list(min(i, len(self.autosort_rules) - 1))

    def move_autosort_rule(self, direction: int):
        i = self.autosort_list.currentRow()
        j = i + direction
        if 0 <= i < len(self.autosort_rules) and 0 <= j < len(self.autosort_rules):
            self.autosort_rules[i], self.autosort_rules[j] = (
                self.autosort_rules[j], self.autosort_rules[i]
            )
            self.persist_autosort()
            self.refresh_autosort_list(j)

    def restore_autosort_defaults(self):
        if QMessageBox.question(
            self, "Restore 30 Autosort defaults?",
            "Replace your current custom rules with the 30 built-in smart "
            "classifiers? Saved clips and existing collections will stay "
            "untouched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        for name in SMART_BINS:
            if name not in self.store.bins():
                self.store.add_bin(name)
                self.tabs.addTab(name)
        self.autosort_rules = default_smart_rules()
        self.persist_autosort()
        # The explicit Restore defaults action is also the one-click upgrade
        # path for an older installation with an empty or disabled rule set.
        self.autosort_switch.setChecked(True)
        self.refresh_autosort_list()
        self.statusBar().showMessage("30 Autosort defaults active", 3500)

    def autosort_destination(
        self, kind: str, text: str, current_bin: str,
        formats: dict[str, bytes] | None = None,
    ):
        if not self.autosort_enabled:
            return current_bin
        return route_clip(
            self.autosort_rules, kind, text, current_bin, self.store.bins(),
            formats=formats,
        )

    def test_autosort(self):
        item = self.history.currentItem()
        if item is None:
            self.autosort_test_result.setText(
                "Select a saved clip in Clipboard, then return here to test."
            )
            return
        payload = self.store.get(item.data(Qt.ItemDataRole.UserRole))
        if payload is None:
            return
        kind, data = payload
        text = data.decode("utf-8", errors="replace") if kind == "text" else ""
        if kind == "text" and looks_sensitive(text):
            message = "The privacy filter would exclude this text from history."
        else:
            formats = self.store.get_formats(
                item.data(Qt.ItemDataRole.UserRole)
            )
            category = classify_smart(kind, text, formats)
            choice = route_clip(
                self.autosort_rules, kind, text, self.active_bin(),
                self.store.bins(), formats=formats,
            )
            label = TYPE_BY_KEY[category].label if category else "Unrecognised"
            message = (
                f"Detected: {label} · excluded from history."
                if choice is None else
                f"Detected: {label} · destination: {choice}"
            )
            if not self.autosort_enabled:
                message += " (Autosort currently disabled)"
        self.autosort_test_result.setText(message)

    def build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Settings · local-only"))
        self.pause_button = QPushButton("Pause monitoring")
        self.pause_button.clicked.connect(self.toggle_monitoring)
        layout.addWidget(self.pause_button)

        login_group = QGroupBox("Start at login")
        login_layout = QVBoxLayout(login_group)
        login_help = QLabel(
            "Optional and OFF by default. Starts ClipMint quietly in the tray "
            "on Cinnamon/X11. Requires the installed .deb; if the system tray "
            "is unavailable, ClipMint opens its window instead."
        )
        login_help.setWordWrap(True)
        login_layout.addWidget(login_help)
        self.login_startup_toggle = QCheckBox("Launch ClipMint when I log in")
        self.login_startup_toggle.setChecked(login_startup_enabled())
        self.login_startup_toggle.toggled.connect(self.set_login_startup_enabled)
        login_layout.addWidget(self.login_startup_toggle)
        layout.addWidget(login_group)

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

        open_files = QPushButton("Open recordings folder")
        open_files.clicked.connect(lambda: self.open_folder(recordings_dir()))
        layout.addWidget(open_files)

        popup_group = QGroupBox("Quick access")
        popup_controls = QVBoxLayout(popup_group)
        popup_help = QLabel(
            "Cinnamon global shortcut: bind /opt/clipmint/ClipMint --toggle "
            "in System Settings → Keyboard → Shortcuts → Custom Shortcuts. "
            "The popup searches all bins without opening the main window."
        )
        popup_help.setWordWrap(True)
        popup_controls.addWidget(popup_help)
        popup_test = QPushButton("Show quick search popup")
        popup_test.clicked.connect(self.toggle_quick_popup)
        popup_controls.addWidget(popup_test)
        popup_controls.addWidget(QLabel("Cinnamon global shortcut (optional):"))
        self.global_popup_hotkey = QKeySequenceEdit()
        self.global_popup_hotkey.setKeySequence(QKeySequence(str(
            self.settings.value("popup/global_shortcut", "Ctrl+Alt+V")
        )))
        popup_controls.addWidget(self.global_popup_hotkey)
        register_button = QPushButton("Register shortcut in Cinnamon…")
        register_button.clicked.connect(self.register_cinnamon_hotkey)
        popup_controls.addWidget(register_button)
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

        # The in-window Ctrl+Shift+S cannot replace Cinnamon shortcuts.
        # Register an independent system-wide command only on explicit request.
        global_screenshot_group = QGroupBox("Screenshot area · global shortcut")
        global_screenshot_layout = QVBoxLayout(global_screenshot_group)
        global_screenshot_help = QLabel(
            "Cinnamon owns system-wide shortcuts. Register Ctrl+Shift+S here "
            "to use ClipMint's region selector even when another app is focused. "
            "If Cinnamon's built-in screenshot action owns the combination, "
            "ClipMint will ask before taking it over, preserve its other "
            "shortcuts and save a reversible backup."
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
        layout.addWidget(global_screenshot_group)

        global_record_group = QGroupBox("Recording area · global shortcut")
        global_record_layout = QVBoxLayout(global_record_group)
        global_record_help = QLabel(
            "Optionally assign Ctrl+Shift+R system-wide to ClipMint's MP4 "
            "region recorder. Desktop or other custom bindings are not "
            "silently replaced."
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
        layout.addWidget(global_record_group)
        audit_button = QPushButton("Check Cinnamon hotkey assignments…")
        audit_button.clicked.connect(self.audit_global_hotkeys)
        layout.addWidget(audit_button)

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
        layout.addWidget(screenshot_group)

        # QSettings holds nonsensitive preferences ONLY; never vault credentials.
        self.shortcut_editors = {}
        self.shortcut_values = {}
        self.shortcut_objects = {}
        shortcut_group = QGroupBox("Keyboard shortcuts")
        shortcut_layout = QVBoxLayout(shortcut_group)
        shortcut_note = QLabel(
            "These shortcuts work when ClipMint is focused. No system-wide "
            "keys are registered, and every action remains mouse-accessible."
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
        layout.addWidget(shortcut_group)
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

    def clipboard_changed(self):
        if (not self.monitoring or self._closing
                or getattr(self.store, "closed", False)):
            return
        if self._ignore_next_clipboard_change:
            self._ignore_next_clipboard_change = False
            return
        data = QApplication.clipboard().mimeData()
        if data is None:
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

    def expire_sensitive_clipboard(self, token: int, expected: str) -> None:
        """Never clear unrelated clipboard content copied in the meantime."""
        if token != self._sensitive_clipboard_token:
            return
        clipboard = QApplication.clipboard()
        if clipboard.text() == expected:
            self._ignore_next_clipboard_change = True
            clipboard.clear()

    def refresh(self, *_args):
        if not hasattr(self, "history"):
            return
        previous = self.selected_id()
        self.history.blockSignals(True)
        self.history.clear()
        bin_name = self.active_bin()
        category = self.category.currentText()
        sort = self.sort_combo.currentData() or self.sort_combo.currentText()
        # Refresh tag choices while preserving the user's current filter.
        current_tag = self.tag_filter.currentData() or ""
        available_tags = self.store.all_tags()
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("All tags", "")
        for tag in available_tags:
            self.tag_filter.addItem("# " + tag, tag)
        index = self.tag_filter.findData(current_tag)
        self.tag_filter.setCurrentIndex(max(0, index))
        self.tag_filter.blockSignals(False)
        clips = self.store.search(
            self.search.text(), bin_name, sort, category,
            tag=self.tag_filter.currentData() or "",
            favorites_only=self.favorites_filter.isChecked(),
        )
        for i, clip in enumerate(clips):
            title = f"{i + 1}. {clip.preview}" if sort == "Numbered list" else clip.preview
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, clip.id)
            kind_tag, _symbol, _color = label_type(clip.kind, clip.preview)
            item.setData(Qt.ItemDataRole.UserRole + 1, {
                "kind": clip.kind, "preview": title,
                "subtitle": "PNG image · clipboard history" if clip.kind == "image"
                    else f"{kind_tag} · clipboard history",
                "age": relative_time(clip.created_at),
                "created": clip.created_at, "pinned": clip.pinned,
                "favorite": clip.favorite,
                "bin": clip.bin, "type": kind_tag,
            })
            item.setToolTip(f"{classify(clip)} · {clip.created_at} · {clip.bin} · "
                            + ", ".join(self.store.tags(clip.id)))
            self.history.addItem(item)
            if clip.id == previous:
                self.history.setCurrentItem(item)
        self.history.blockSignals(False)
        self.count_label.setText(f"{len(clips):02d} / {self.store.count(bin_name):02d}")
        self.search.setToolTip(self.store.index_status())
        self._refresh_queue_button()
        if hasattr(self, "footer_status"):
            self.footer_status.setText(f"● Ready   |   HISTORY {self.store.count(bin_name):02d}")
        if hasattr(self, "footer_status"):
            self.footer_status.setToolTip(f"{self.store.count(bin_name)} clips in {bin_name}")
        if self.history.currentItem() is None:
            self.clear_preview()
        else:
            self.preview_clip(self.history.currentItem(), None)

    def clear_preview(self) -> None:
        self.preview_image.clear_image()
        self.preview_label.setText("Select an item to preview")
        self.preview_stack.setCurrentWidget(self.preview_label)
        self.preview_name.setText("No selection")
        self.preview_sub.setText("Select a clipboard entry")
        for field in self.preview_meta.values():
            field.setText("—")
        for action in (self.copy_action, self.pin_action, self.delete_action):
            action.setEnabled(False)

    def preview_clip(self, current, _old):
        if current is None:
            self.clear_preview()
            return
        clip_id = current.data(Qt.ItemDataRole.UserRole)
        value = self.store.get(clip_id)
        if value is None:
            self.clear_preview()
            return
        for action in (self.copy_action, self.pin_action, self.delete_action):
            action.setEnabled(True)
        meta = current.data(Qt.ItemDataRole.UserRole + 1) or {}
        kind, contents = value
        self.preview_name.setText(meta.get("preview", current.text()))
        tag = meta.get("type", "IMG" if kind == "image" else "FILE" if kind == "files" else "TXT")
        self.preview_meta["Type"].setText("Image / PNG" if kind == "image" else "Files / URI" if kind == "files" else f"Text / {tag}")
        self.preview_meta["Saved"].setText(meta.get("age", "—") + " ago" if meta.get("age") not in (None, "now", "—") else meta.get("age", "—"))
        self.preview_meta["Collection"].setText(meta.get("bin", self.active_bin()))
        self.preview_meta["Source"].setText("Clipboard image" if kind == "image" else "Clipboard files" if kind == "files" else "Clipboard text")
        self.preview_meta["Tags"].setText(", ".join(self.store.tags(clip_id)) or "—")
        self.pin_action.setText("UNPIN" if self.store.pinned(clip_id) else "PIN")
        if kind in ("text", "files"):
            self.preview_image.clear_image()
            self.preview_label.setText(contents.decode("utf-8", errors="replace")[:5000])
            self.preview_sub.setText(f"{'FILES' if kind == 'files' else 'TEXT'} · {len(contents):,} bytes")
            self.preview_stack.setCurrentWidget(self.preview_label)
            return
        self.preview_sub.setText("IMAGE FILE · PNG")
        if len(contents) > 16 * 1024 * 1024:
            self.preview_label.setText("Image too large to preview")
            self.preview_stack.setCurrentWidget(self.preview_label)
            return
        # Prevent hostile oversized PNG dimensions from exhausting Qt memory.
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
        self.preview_sub.setText(f"IMAGE · {image.width()} × {image.height()} · PNG · {len(contents):,} B")
        self.preview_stack.setCurrentWidget(self.preview_image_page)
        self.preview_image.show_image(image)

    def toggle_pin_selected(self):
        clip_id = self.selected_id()
        if clip_id is None:
            return
        self.store.pin(clip_id, not self.store.pinned(clip_id))
        self.refresh()

    def toggle_favorite_selected(self):
        clip_id = self.selected_id()
        if clip_id is None:
            return
        self.store.favorite(clip_id, not self.store.is_favorite(clip_id))
        self.refresh()

    def edit_selected_tags(self):
        clip_id = self.selected_id()
        if clip_id is None:
            return
        original = ", ".join(self.store.tags(clip_id))
        value, ok = QInputDialog.getText(
            self, "Archive tags", "Comma-separated labels (letters, numbers, - or _):",
            text=original,
        )
        if not ok:
            return
        try:
            self.store.set_tags(clip_id, [tag for tag in value.split(",") if tag.strip()])
        except ValueError as exc:
            self.error("Tags", str(exc))
            return
        self.refresh()

    def _copy_plain_text(self, value: str):
        self._ignore_next_clipboard_change = True
        QApplication.clipboard().setText(value)
        QTimer.singleShot(400, lambda: setattr(self, "_ignore_next_clipboard_change", False))
        self.statusBar().showMessage("Copied to clipboard · Paste manually", 5000)

    def _copy_entry_by_id(self, clip_id: int) -> bool:
        entry = self.store.get(clip_id)
        if entry is None:
            return False
        kind, contents = entry
        self._ignore_next_clipboard_change = True
        QApplication.clipboard().setMimeData(
            mime_from_entry(kind, contents, self.store.get_formats(clip_id))
        )
        QTimer.singleShot(400, lambda: setattr(self, "_ignore_next_clipboard_change", False))
        self.store.refresh_temporary_copy_time(clip_id)
        return True

    def show_templates(self):
        dialog = TemplatesDialog(self.store, self._copy_plain_text, self)
        dialog.exec()

    def make_selected_template(self):
        clip_id = self.selected_id()
        entry = self.store.get(clip_id) if clip_id is not None else None
        if not entry or entry[0] != "text":
            return
        name, ok = QInputDialog.getText(
            self, "Save reusable snippet", "Template name:"
        )
        if not ok or not name.strip():
            return
        body = entry[1].decode("utf-8", "replace")
        if looks_sensitive(body) or sensitive_text(body):
            self.error("Snippet templates", "Potential credentials cannot be saved as a template")
            return
        try:
            self.store.save_template(name, body)
        except (ValueError, Exception) as exc:
            self.error("Snippet templates", str(exc))
            return
        self.inform("Snippet saved", "Use the Snippets button to fill and copy it")

    def transform_selected(self):
        clip_id = self.selected_id()
        entry = self.store.get(clip_id) if clip_id is not None else None
        if not entry or entry[0] != "text":
            return
        content = entry[1].decode("utf-8", "replace")
        if looks_sensitive(content) or sensitive_text(content):
            self.error("Text workshop", "Potential credentials are excluded from transformations")
            return
        dialog = TransformDialog(content, self._copy_plain_text,
                                 self._save_transformed_text, self)
        dialog.exec()

    def _save_transformed_text(self, value: str):
        if not value:
            self.inform("Text workshop", "No text to save")
            return
        if looks_sensitive(value) or sensitive_text(value):
            self.error("Text workshop", "Potential credentials are not saved in history")
            return
        raw = value.encode("utf-8")
        self.store.add("text", raw, " ".join(value.split())[:550],
                       self.active_bin(), formats={"text/plain;charset=utf-8": raw})
        self.refresh()
        self.inform("Text workshop", "Saved as a new clip; the original is unchanged")

    def queue_add_selected(self):
        clip_id = self.selected_id()
        if clip_id is None:
            return
        try:
            added = self.paste_queue.add(clip_id)
        except ValueError as exc:
            self.error("Paste queue", str(exc))
            return
        self._refresh_queue_button()
        self.statusBar().showMessage(
            "Added to paste queue" if added else "Already in paste queue", 4500
        )

    def _refresh_queue_button(self):
        if not hasattr(self, "queue_next_button"):
            return
        count = len(self.paste_queue)
        self.queue_next_button.setText(f"NEXT {count}")
        self.queue_next_button.setEnabled(bool(count))
        self.queue_next_button.setToolTip(
            f"{count} queued · copy next item; paste manually (never types into other windows)"
        )

    def queue_copy_next(self):
        while len(self.paste_queue):
            clip_id = self.paste_queue.next_id()
            self._refresh_queue_button()
            if clip_id is not None and self._copy_entry_by_id(clip_id):
                self.inform("Paste queue", "Next item copied; paste manually, then choose NEXT")
                return
        self.statusBar().showMessage("Paste queue is empty", 3500)

    def queue_clear(self):
        if not len(self.paste_queue):
            return
        result = QMessageBox.question(
            self, "Clear paste queue", "Clear all queued items? Saved clips will remain.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.paste_queue.clear()
            self._refresh_queue_button()

    def delete_selected(self):
        clip_id = self.selected_id()
        if clip_id is None:
            return
        result = QMessageBox.question(
            self, "Delete clipboard item",
            "Permanently delete the selected history item?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.store.delete(clip_id)
            self.refresh()

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
        is_image = (self.store.get(clip_id) or ("", b""))[0] == "image"
        ocr_action = menu.addAction("OCR · Extract text from image") if is_image else None
        pin = menu.addAction("Unpin" if pinned else "Pin")
        favorite = menu.addAction(
            "Remove favourite" if self.store.is_favorite(clip_id) else "Add to favourites"
        )
        edit_tags = menu.addAction("Edit tags…")
        queue_item = menu.addAction("Add to paste queue")
        menu.addSeparator()
        is_text = (self.store.get(clip_id) or ("", b""))[0] == "text"
        make_template = menu.addAction("Save as snippet template…") if is_text else None
        transform = menu.addAction("Text workshop · Preview transform…") if is_text else None
        menu.addSeparator()
        move_menu = menu.addMenu("Move to bin")
        moves = {}
        for name in self.store.bins():
            if name != self.active_bin():
                moves[move_menu.addAction(name)] = name
        delete = menu.addAction("Delete")
        choice = menu.exec(self.history.viewport().mapToGlobal(position))
        if choice == copy:
            self.copy_clip(item)
        elif choice is not None and choice == ocr_action:
            self.ocr_history_clip(clip_id)
        elif choice == pin:
            self.store.pin(clip_id, not pinned)
            self.refresh()
        elif choice == favorite:
            self.toggle_favorite_selected()
        elif choice == edit_tags:
            self.edit_selected_tags()
        elif choice == queue_item:
            self.queue_add_selected()
        elif choice is not None and choice == make_template:
            self.make_selected_template()
        elif choice is not None and choice == transform:
            self.transform_selected()
        elif choice in moves:
            self.store.move(clip_id, moves[choice])
            self.refresh()
        elif choice == delete:
            self.store.delete(clip_id)
            self.refresh()

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
        worker = OcrWorker(png, self)
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
        self._ignore_next_clipboard_change = True
        QApplication.clipboard().setText(text)
        QTimer.singleShot(400, lambda: setattr(self, "_ignore_next_clipboard_change", False))
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
        self._ignore_next_clipboard_change = True
        QTimer.singleShot(400, lambda: setattr(self, "_ignore_next_clipboard_change", False))
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
        executable = (shlex.quote(sys.executable)
                      if getattr(sys, "frozen", False) else
                      shlex.quote(sys.executable) + " " +
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
        self._ignore_next_clipboard_change = True
        if plain:
            QApplication.clipboard().setText(content.decode("utf-8", "replace"))
        else:
            QApplication.clipboard().setMimeData(
                mime_from_entry(kind, content, self.store.get_formats(clip_id))
            )
        QTimer.singleShot(400, lambda: setattr(self, "_ignore_next_clipboard_change", False))
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

    def enable_encrypted_history(self):
        if self.history_secure:
            return
        confirmation = QMessageBox.question(
            self, "Encrypt clipboard history",
            "This creates a separate encrypted SQLite database using your unlocked "
            "desktop Secret Service keyring. The original plaintext database is "
            "preserved for recovery, and will still require manual removal. Continue?",
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
        self.store.close()
        self.store = secure
        self.quick_popup.store = secure
        self.history_secure = True
        self.history_security_error = ""
        self.monitoring = True
        self.settings.setValue("privacy/history_secure", True)
        self.secure_history_button.setText("Encrypted history active")
        self.secure_history_button.setEnabled(False)
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
        self.notify_screenshot_captured(path)
        # If the user visits the archive after capturing, preselect the new PNG.
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
                12000, lambda: self.dismiss_screenshot_notice(token)
            )
        if self.tray is not None:
            self._last_tray_notification = "screenshot"
            self.tray.showMessage(
                "Screenshot captured",
                "Click here to edit your screenshot.",
                QSystemTrayIcon.MessageIcon.Information, 10000,
            )

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
        self.lock_vault()
        if self._closing:
            event.accept()
        elif self.tray is not None:
            self.hide()
            event.ignore()
        elif self.recorder.process is not None:
            self.error("Recording active", "Finish recording before quitting")
            event.ignore()
        else:
            self.clear_temporary_on_normal_exit()
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
    elif command in ("screenshot-area", "record-area"):
        window.show()
        if command == "screenshot-area":
            QTimer.singleShot(150, window.choose_screenshot)
        else:
            QTimer.singleShot(150, lambda: window.choose_recording("MP4"))
    elif hidden and window.tray is not None:
        # Login startup stays headless but is reachable through the tray.
        app.setQuitOnLastWindowClosed(False)
    else:
        # Never leave a background watcher inaccessible on desktops with no tray.
        window.show()
    raise SystemExit(app.exec())
