"""ClipMint: self-contained, mouse-first clipboard bins and screen capture for Cinnamon X11."""
from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys

from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice, QTimer, QSettings
from PySide6.QtGui import QImage, QFont, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QPushButton, QStyle, QSystemTrayIcon,
    QTabBar, QToolButton, QVBoxLayout, QWidget, QStackedWidget, QSizePolicy,
    QKeySequenceEdit, QGroupBox, QCheckBox, QDialogButtonBox,
    QFormLayout, QAbstractItemView,
)

from .branding import ChromaticWordmark, register_display_font
from .manga import CrimsonMaidPortrait
from .crimson_ui import build_crimson_ui, relative_time, label_type
from .capture import AreaSelector, RegionRecorder, recordings_dir, screenshots_dir, stamped_filename
from .recording_ui import RecorderWindow, SaveClipDialog
from .store import ClipStore, classify, looks_sensitive
from .autosort import RULE_TYPES, NEVER_CAPTURE, validate_rule, route_clip


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
        self.recorder = RegionRecorder()
        self.monitoring = True
        self.selector: AreaSelector | None = None
        self.recorder_window: RecorderWindow | None = None
        self.capture_rect = None
        self.capture_format = "MP4"
        self._privacy_skipped = 0
        self._closing = False
        self._ignore_next_clipboard_change = False

        # Native reconstruction of the approved Crimson Archive v2 prototype.
        # All content comes from the existing history store and capture methods.
        self.wordmark = ChromaticWordmark(self.brand_family)
        build_crimson_ui(self, ImagePreviewLabel)
        self.build_library_page("Screenshots")
        self.build_library_page("Recordings")
        self.build_info_page("Secrets & Variables", (
            "Private by default\n\n"
            "This preview does NOT contain an encrypted vault. Saved clipboard "
            "history remains unencrypted. Avoid storing passwords or API keys.\n\n"
            "Credentials are only heuristically excluded from clipboard monitoring."
        ))
        self.build_autosort_page()
        self.build_settings_page()
        self.install_shortcuts()
        self.statusBar().showMessage("Ready · Left-click to preview, right-click for Copy / Pin / Move / Delete")
        self.configure_tray()
        QApplication.clipboard().dataChanged.connect(self.clipboard_changed)
        self.poller = QTimer(self)
        self.poller.timeout.connect(self.poll_recording)
        self.poller.start(300)
        self.open_section(0)
        self._update_manga_visibility()
        QTimer.singleShot(400, self.clipboard_changed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "manga_dock"):
            self._update_manga_visibility()

    def _update_manga_visibility(self):
        # Approved prototype: full portrait above compact threshold; protect
        # useful clipboard/preview real estate on smaller screens.
        show = self.width() >= 1000 and self.height() >= 650
        self.manga_dock.setVisible(show)
        if show:
            self.manga_dock.setFixedWidth(
                336 if self.width() < 1140 else min(390, max(305, int(self.width() * .26)))
            )
        self.dock_panel.setFixedWidth(110 if self.width() >= 1370 else 56)
        if hasattr(self, "archive_heading"):
            self.archive_heading.setText(
                "Clipboard  ·  クリップボード" if self.width() >= 1270 else "Clipboard"
            )
        if hasattr(self, "preview_heading"):
            self.preview_heading.setText(
                "プレビュー / PREVIEW" if self.width() >= 1370 else "プレビュー"
            )
        icons = {"Clipboard":"▤", "Screenshots":"▣", "Recordings":"◉",
                 "Secrets & Variables":"♢", "Autosort":"⇄", "Settings":"⚙"}
        for label, button in self.nav_buttons.items():
            if self.width() >= 1370:
                short = {"Screenshots":"Shots", "Recordings":"Video",
                         "Secrets & Variables":"Secrets"}.get(label, label)
                button.setText(icons[label] + "\n" + short.upper())
                button.setMinimumHeight(73)
            else:
                button.setText(icons[label])
                button.setMinimumHeight(60)

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

    def build_autosort_page(self):
        """Native Qt rule editor. Autosort is OFF unless explicitly enabled."""
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Autosort · routing rules")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        summary = QLabel(
            "Rules are checked top-to-bottom. The first matching enabled rule "
            "wins; without a match, clips stay in your selected bin. "
            "This does not replace manual sorting or delete saved history."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        self.autosort_enabled = self.settings.value(
            "autosort/enabled", False, type=bool
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
                f"{rule['mode']}: {rule['pattern']}" if rule["mode"] in
                ("Keyword", "Regex") else rule["mode"]
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
        destination = QComboBox()
        destination.addItems([*self.store.bins(), NEVER_CAPTURE])
        enabled = QCheckBox("Rule enabled")
        enabled.setChecked(original.get("enabled", True) if original else True)
        form.addRow("Match", mode)
        form.addRow("Keyword / regex", pattern)
        form.addRow("Then", destination)
        form.addRow("", enabled)
        if original:
            mode.setCurrentText(original["mode"])
            pattern.setText(original["pattern"])
            destination.setCurrentText(original["target"])
        mode.currentTextChanged.connect(
            lambda text: pattern.setEnabled(text in ("Keyword", "Regex"))
        )
        pattern.setEnabled(mode.currentText() in ("Keyword", "Regex"))
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
                    "pattern": pattern.text(),
                    "target": destination.currentText(),
                    "enabled": enabled.isChecked(),
                }, self.store.bins())
            except ValueError as exc:
                QMessageBox.warning(dialog, "Invalid Autosort rule", str(exc))
        return None

    def add_autosort_rule(self):
        rule = self.edit_autosort_dialog()
        if rule is not None:
            self.autosort_rules.append(rule)
            self.persist_autosort()
            self.refresh_autosort_list(len(self.autosort_rules) - 1)

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

    def autosort_destination(self, kind: str, text: str, current_bin: str):
        if not self.autosort_enabled:
            return current_bin
        return route_clip(
            self.autosort_rules, kind, text, current_bin, self.store.bins()
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
            choice = route_clip(
                self.autosort_rules, kind, text, self.active_bin(),
                self.store.bins(),
            )
            message = (
                "This new clip would be excluded from history."
                if choice is None else f"This new clip would go to: {choice}"
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
        open_files = QPushButton("Open recordings folder")
        open_files.clicked.connect(lambda: self.open_folder(recordings_dir()))
        layout.addWidget(open_files)

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
        layout.addWidget(QLabel("History is stored locally and is not encrypted."))
        layout.addStretch()
        self.pages.addWidget(page)

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
        if (not self.monitoring or self._closing
                or getattr(self.store, "closed", False)):
            return
        if self._ignore_next_clipboard_change:
            self._ignore_next_clipboard_change = False
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
                target = self.autosort_destination("image", "", active)
                if target is None:
                    self.statusBar().showMessage("Image excluded by Autosort rule", 4000)
                else:
                    self.store.add("image", bytes(result), f"Image {picture.width()} × {picture.height()}", target)
        elif data.hasText():
            text = data.text()
            if text.strip():
                if looks_sensitive(text):
                    self._privacy_skipped += 1
                    self.statusBar().showMessage("Potential credential excluded from history")
                    return
                payload = text.encode("utf-8")
                if len(payload) <= 2 * 1024 * 1024:
                    target = self.autosort_destination("text", text, active)
                    if target is None:
                        self.statusBar().showMessage("Text excluded by Autosort rule", 4000)
                    else:
                        self.store.add("text", payload, " ".join(text.split())[:550], target)
        self.refresh()

    def refresh(self, *_args):
        if not hasattr(self, "history"):
            return
        previous = self.selected_id()
        self.history.blockSignals(True)
        self.history.clear()
        bin_name = self.active_bin()
        category = self.category.currentText()
        sort = self.sort_combo.currentData() or self.sort_combo.currentText()
        clips = self.store.search(self.search.text(), bin_name, sort, category)
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
                "bin": clip.bin, "type": kind_tag,
            })
            item.setToolTip(f"{classify(clip)} · {clip.created_at} · {clip.bin}")
            self.history.addItem(item)
            if clip.id == previous:
                self.history.setCurrentItem(item)
        self.history.blockSignals(False)
        self.count_label.setText(f"{len(clips):02d} / {self.store.count(bin_name):02d}")
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
        tag = meta.get("type", "IMG" if kind == "image" else "TXT")
        self.preview_meta["Type"].setText("Image / PNG" if kind == "image" else f"Text / {tag}")
        self.preview_meta["Saved"].setText(meta.get("age", "—") + " ago" if meta.get("age") not in (None, "now", "—") else meta.get("age", "—"))
        self.preview_meta["Collection"].setText(meta.get("bin", self.active_bin()))
        self.preview_meta["Source"].setText("Clipboard image" if kind == "image" else "Clipboard text")
        self.pin_action.setText("UNPIN" if self.store.pinned(clip_id) else "PIN")
        if kind == "text":
            self.preview_image.clear_image()
            self.preview_label.setText(contents.decode("utf-8", errors="replace")[:5000])
            self.preview_sub.setText(f"TEXT · {len(contents):,} bytes")
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
        # A deliberate "Copy" action should not be re-recorded as a new
        # history entry; Qt emits dataChanged for our own clipboard write.
        self._ignore_next_clipboard_change = True
        QTimer.singleShot(400, lambda: setattr(self, "_ignore_next_clipboard_change", False))
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
