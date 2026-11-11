"""Settings preference callbacks and window-local shortcut handling.

The Qt Settings view is assembled by settings_page, keeping UI construction
separate from state-changing actions and storage confirmation prompts.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMessageBox

from .ocr import validate_language
from .settings_page import SHORTCUT_SPECS, WheelSafeHistoryLimitComboBox, build_settings_page


class SettingsControllerMixin:
    """Preferences and Settings signals for ClipMintWindow."""

    def build_settings_page(self):
        """Populate the Settings page through the dedicated view module."""
        return build_settings_page(self)

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

