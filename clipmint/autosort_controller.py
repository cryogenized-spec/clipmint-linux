"""Autosort rule-editor/controller extracted from the main ClipMint window.

This module handles visible rule editing and the existing smart-routing
decisions. It deliberately does not change the persisted rule schema, rule
evaluation order, sensitive text blocking, or clipboard capture lifecycle.
"""
from __future__ import annotations

import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from .autosort import RULE_TYPES, NEVER_CAPTURE, validate_rule, route_clip
from .smart_types import (
    SMART_TYPES, TYPE_BY_KEY, DEFAULT_BINS as SMART_BINS,
    classify_smart, default_smart_rules,
)
from .store import looks_sensitive


class AutosortControllerMixin:
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
                self.bin_filter.addItem(name, name)
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

