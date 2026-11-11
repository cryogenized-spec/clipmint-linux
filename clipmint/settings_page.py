"""Settings page construction and widget definitions.

This module owns the Qt view. Preference changes and security-sensitive
callbacks stay on SettingsControllerMixin, invoked through the main window.
The previously public shortcut specification and wheel-safe selector retain
their object identities through re-exports from settings_controller.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGroupBox, QHBoxLayout, QKeySequenceEdit,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QTabWidget,
    QVBoxLayout, QWidget,
)

from .autostart import is_enabled as login_startup_enabled
from .capture import recordings_dir
from .foreground_privacy import DEFAULT_BLOCKED
from .ocr import validate_language
from .screenshot_editor import installed_editors
from .updater import installed_version


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


def build_settings_page(self):
    """Assemble independently scoped Settings groups in their display order."""
    page = QWidget()
    layout = QVBoxLayout(page)
    _add_startup_updates(self, layout)
    _add_history_retention(self, layout)
    _add_ocr_popup(self, layout)
    local_layout = _add_global_shortcuts(self, layout)
    _add_privacy(self, layout)
    _add_capture_preferences(self, layout)
    _add_local_shortcuts(self, layout, local_layout)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(page)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    self.pages.addWidget(scroll)




def _add_startup_updates(self, layout):
    """Compose the startup updates Settings controls."""
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
        "Manual checking is the default. You may opt into background "
        "availability checks, but ClipMint never downloads packages in "
        "the background while independent release signing is pending. "
        "Download available preview requires explicit approval and shows "
        "the full installer size, even if a smaller patch is available. "
        "Checksums verify integrity, NOT independent publisher identity. "
        "Installation always requires Linux Mint package-manager approval."
    )
    update_help.setWordWrap(True)
    update_layout.addWidget(update_help)
    self.auto_update_toggle = QCheckBox(
        "Check for new previews automatically (no background downloads)"
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



def _add_history_retention(self, layout):
    """Compose the history retention Settings controls."""
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



def _add_ocr_popup(self, layout):
    """Compose the ocr popup Settings controls."""
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



def _add_global_shortcuts(self, layout):
    """Compose the global shortcuts Settings controls."""
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
    return local_layout



def _add_privacy(self, layout):
    """Compose the privacy Settings controls."""
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



def _add_capture_preferences(self, layout):
    """Compose the capture preferences Settings controls."""
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



def _add_local_shortcuts(self, layout, local_layout):
    """Compose the local shortcuts Settings controls."""
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

