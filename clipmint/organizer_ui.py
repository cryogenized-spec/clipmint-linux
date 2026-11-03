"""Native Qt dialogs for reusable snippets and explicit text transforms.

No template evaluation, network activity, or unattended keyboard injection.
The original clipboard item remains unchanged unless the user creates a new
entry explicitly.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMessageBox, QInputDialog,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from .productivity import TRANSFORMS, render_template, template_fields, transform_text


class TemplatesDialog(QDialog):
    def __init__(self, store, on_copy, parent=None):
        super().__init__(parent)
        self.store = store
        self.on_copy = on_copy
        self.setWindowTitle("Kohaku Archive · Snippet templates")
        self.resize(720, 540)
        root = QVBoxLayout(self)
        title = QLabel("SNIPPET ARCHIVE / 再利用")
        title.setStyleSheet('font:italic 24px "Cormorant Garamond";color:#F3D8C7')
        root.addWidget(title)
        note = QLabel(
            "Templates are stored locally. Standard history is not encrypted; "
            "avoid passwords and access tokens. {{name}} inserts a prompted value."
        )
        note.setWordWrap(True)
        root.addWidget(note)
        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMinimumWidth(185)
        self.list.currentRowChanged.connect(self.select_template)
        body.addWidget(self.list, 1)
        right = QWidget()
        form = QVBoxLayout(right)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Template name")
        form.addWidget(self.name)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Dear {{customer}},\nYour order is ready for collection.")
        form.addWidget(self.editor, 1)
        buttons = QHBoxLayout()
        self.new_btn = QPushButton("New")
        self.new_btn.clicked.connect(self.new_template)
        buttons.addWidget(self.new_btn)
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save_template)
        buttons.addWidget(self.save_btn)
        self.use_btn = QPushButton("Fill & copy")
        self.use_btn.clicked.connect(self.use_template)
        buttons.addWidget(self.use_btn)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_template)
        buttons.addWidget(self.delete_btn)
        form.addLayout(buttons)
        body.addWidget(right, 3)
        root.addLayout(body, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        root.addWidget(close)
        self.current_id = None
        self.reload()

    def reload(self, selected=None):
        self.list.blockSignals(True)
        self.list.clear()
        for template_id, name, _ in self.store.templates():
            self.list.addItem(f"{template_id} · {name}")
            self.list.item(self.list.count()-1).setData(256, template_id)
        self.list.blockSignals(False)
        if selected is not None:
            for i in range(self.list.count()):
                if self.list.item(i).data(256) == selected:
                    self.list.setCurrentRow(i)
                    break

    def select_template(self, row):
        if row < 0:
            return
        template_id = self.list.item(row).data(256)
        for ident, name, body in self.store.templates():
            if ident == template_id:
                self.current_id = ident
                self.name.setText(name)
                self.editor.setPlainText(body)
                return

    def new_template(self):
        self.current_id = None
        self.list.clearSelection()
        self.name.clear()
        self.editor.clear()
        self.name.setFocus()

    def save_template(self):
        try:
            ident = self.store.save_template(
                self.name.text(), self.editor.toPlainText(), self.current_id
            )
        except Exception as exc:
            QMessageBox.warning(self, "Template not saved", str(exc))
            return
        self.current_id = ident
        self.reload(selected=ident)

    def use_template(self):
        body = self.editor.toPlainText()
        values = {}
        for field in template_fields(body):
            value, ok = QInputDialog.getText(
                self, "Fill template", f"Value for {{{{{field}}}}}:"
            )
            if not ok:
                return
            values[field] = value
        try:
            output = render_template(body, values)
        except ValueError as exc:
            QMessageBox.warning(self, "Template cannot be used", str(exc))
            return
        if not output:
            QMessageBox.information(self, "Template", "There is no text to copy")
            return
        self.on_copy(output)
        self.accept()

    def delete_template(self):
        if self.current_id is None:
            return
        if QMessageBox.question(
            self, "Delete template", "Permanently delete this snippet template?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.store.delete_template(self.current_id)
        self.current_id = None
        self.name.clear()
        self.editor.clear()
        self.reload()


class TransformDialog(QDialog):
    def __init__(self, text: str, on_copy, on_save, parent=None):
        super().__init__(parent)
        self.original = text
        self.on_copy = on_copy
        self.on_save = on_save
        self.setWindowTitle("Kohaku Archive · Text workshop")
        self.resize(730, 540)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Preview before applying. The original history item is never modified."
        ))
        self.operation = QComboBox()
        self.operation.addItems(TRANSFORMS)
        self.operation.currentTextChanged.connect(self.update_preview)
        layout.addWidget(self.operation)
        self.preview = QPlainTextEdit()
        self.preview.setPlaceholderText("Transformation preview")
        layout.addWidget(self.preview, 1)
        buttons = QHBoxLayout()
        for title, func in (
            ("Revert", self.revert),
            ("Copy preview", self.copy_preview),
            ("Save as new clip", self.save_preview),
            ("Close", self.reject)
        ):
            button = QPushButton(title)
            button.clicked.connect(func)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.update_preview()

    def update_preview(self, *_):
        try:
            self.preview.setPlainText(transform_text(self.original, self.operation.currentText()))
        except (ValueError, TypeError) as exc:
            self.preview.setPlainText(self.original)
            QMessageBox.warning(self, "Transformation unavailable", str(exc))

    def revert(self):
        self.preview.setPlainText(self.original)

    def copy_preview(self):
        self.on_copy(self.preview.toPlainText())
        self.accept()

    def save_preview(self):
        self.on_save(self.preview.toPlainText())
        self.accept()
