"""Clipboard history presentation, preview, actions and context menus.

This controller keeps ClipMint's existing clipboard UI behavior while
separating it from the main window constructor and capture event loop.
The history database, sensitive-content filters and watcher are unchanged.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication, QInputDialog, QListWidgetItem, QMenu, QMessageBox,
)

from .store import classify, looks_sensitive
from .clipboard_formats import sensitive_text
from .history_clipboard_copy import copy_saved_clip, CopyOutcome
from .crimson_ui import relative_time, label_type
from .history_filters import selected_category
from .organizer_ui import TemplatesDialog, TransformDialog


class HistoryControllerMixin:
    def refresh(self, *_args):
        self._history_search_timer.stop()
        if not hasattr(self, "history"):
            return
        previous = self.selected_id()
        self.history.blockSignals(True)
        self.history.clear()
        bin_name = self.view_bin()
        category = selected_category(self.tabs)
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
        show_labels = (
            self.settings.value("history/show_clip_labels", False, type=bool)
            and category == "All"
        )
        for i, clip in enumerate(clips):
            # Both the stored preview and default UI are free of prefixes.
            # Optional collection labels are presentation-only in All clips.
            title = f"{i + 1}. {clip.preview}" if sort == "Numbered list" else clip.preview
            if show_labels:
                title = f"[{clip.bin}]  {title}"
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, clip.id)
            kind_tag, _symbol, _color = label_type(clip.kind, clip.preview)
            item.setData(Qt.ItemDataRole.UserRole + 1, {
                "kind": clip.kind, "preview": title,
                "raw_preview": clip.preview,
                "show_badges": show_labels,
                "subtitle": (
                    ("PNG image" if clip.kind == "image" else kind_tag)
                    + " · clipboard history"
                ) if show_labels else "Clipboard history",
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
        if self.history_secure and self.store.corrupt_row_ids:
            self.statusBar().showMessage(
                f"Warning: {len(self.store.corrupt_row_ids)} encrypted history "
                "item(s) could not be decrypted and are hidden, not deleted.",
                15000,
            )
        self._refresh_queue_button()
        if hasattr(self, "footer_status"):
            state = ("HISTORY LOCKED" if self.history_security_error
                     else "MONITORING ACTIVE" if self.monitoring
                     else "MONITORING PAUSED")
            self.footer_status.setText(
                f"● {state}   |   HISTORY {self.store.count(bin_name):02d}"
            )
        if hasattr(self, "footer_status"):
            scope = "all collections" if bin_name is None else bin_name
            self.footer_status.setToolTip(
                f"{self.store.count(bin_name)} clips in {scope}"
            )
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
        self._own_clipboard_guard.note_text(value)
        QApplication.clipboard().setText(value)
        self.statusBar().showMessage("Copied to clipboard · Paste manually", 5000)

    def _copy_entry_by_id(self, clip_id: int) -> bool:
        return copy_saved_clip(
            self.store, lambda: self._own_clipboard_guard,
            QApplication.clipboard, clip_id,
        ) == CopyOutcome.COPIED

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

    def move_destinations_for_item(self, item) -> list[str]:
        """Offer every bin except the selected clip's *actual* collection.

        The All clips stream has no physical destination of its own. Do not
        conflate the Work fallback for new writes with an existing item's bin.
        """
        details = item.data(Qt.ItemDataRole.UserRole + 1) or {}
        current = details.get("bin") if isinstance(details, dict) else None
        return [name for name in self.store.bins() if name != current]

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
        for name in self.move_destinations_for_item(item):
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

