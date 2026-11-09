"""Safety and delegation contracts for the extracted history UI.

No live clipboard access, external network or production history DB required.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from clipmint.app import ClipMintWindow
from clipmint.history_controller import HistoryControllerMixin


class HistoryControllerRefactorTests(unittest.TestCase):
    def test_main_window_preserves_history_callbacks(self):
        self.assertTrue(issubclass(ClipMintWindow, HistoryControllerMixin))
        for method in (
            "refresh", "clear_preview", "preview_clip",
            "toggle_pin_selected", "toggle_favorite_selected",
            "edit_selected_tags", "_copy_plain_text",
            "_copy_entry_by_id", "show_templates", "make_selected_template",
            "transform_selected", "_save_transformed_text",
            "queue_add_selected", "_refresh_queue_button",
            "queue_copy_next", "queue_clear", "delete_selected",
            "selected_id", "move_destinations_for_item", "context_menu",
        ):
            with self.subTest(method=method):
                self.assertIs(
                    getattr(ClipMintWindow, method),
                    getattr(HistoryControllerMixin, method),
                )

    def test_history_movement_uses_saved_bin_not_all_clips_filter(self):
        state = SimpleNamespace(
            store=SimpleNamespace(bins=lambda: ["Work", "Personal", "Temporary"])
        )
        row = SimpleNamespace(data=lambda role: {"bin": "Personal"})
        self.assertEqual(
            HistoryControllerMixin.move_destinations_for_item(state, row),
            ["Work", "Temporary"],
        )

    def test_clipboard_copy_does_not_use_missing_database_entry(self):
        state = SimpleNamespace(store=SimpleNamespace(get=lambda _id: None))
        self.assertFalse(HistoryControllerMixin._copy_entry_by_id(state, 12))

    def test_sensitive_text_cannot_be_saved_as_a_snippet(self):
        store = SimpleNamespace(
            get=lambda _id: ("text", b"password: exampleSecret1234"),
            save_template=Mock(),
        )
        state = SimpleNamespace(
            selected_id=lambda: 42, store=store, error=Mock(),
        )
        # Production first asks for the snippet title, then checks the text.
        # Simulate only that modal dialog; never show real Qt UI in this test.
        with patch("clipmint.history_controller.QInputDialog.getText",
                   return_value=("Unsafe snippet", True)):
            HistoryControllerMixin.make_selected_template(state)
        store.save_template.assert_not_called()
        state.error.assert_called_once()
        self.assertEqual(state.error.call_args.args[0], "Snippet templates")

    def test_sensitive_text_is_excluded_from_transformations(self):
        state = SimpleNamespace(
            selected_id=lambda: 42,
            store=SimpleNamespace(get=lambda _id: (
                "text", b"password: exampleSecret1234",
            )),
            error=Mock(),
        )
        HistoryControllerMixin.transform_selected(state)
        state.error.assert_called_once()
        self.assertEqual(state.error.call_args.args[0], "Text workshop")

    def test_no_delete_without_explicit_confirmation(self):
        store = SimpleNamespace(delete=Mock())
        state = SimpleNamespace(
            selected_id=lambda: 5, store=store, refresh=Mock(),
        )
        with patch("clipmint.history_controller.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.No):
            HistoryControllerMixin.delete_selected(state)
        store.delete.assert_not_called()
        state.refresh.assert_not_called()

    def test_oversized_png_dimensions_still_block_previews(self):
        png_header = (
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
            + (100_000).to_bytes(4, "big")
            + (100_000).to_bytes(4, "big")
        )
        # The preview must reject the dimensions before attempting Qt
        # decoding, retaining the original pixel-count safety bound.
        store = SimpleNamespace(
            get=lambda _id: ("image", png_header),
            tags=lambda _id: [], pinned=lambda _id: False,
        )
        current = SimpleNamespace(
            data=lambda role: (7 if role == Qt.ItemDataRole.UserRole else {}),
            text=lambda: "image",
        )
        preview_meta = {k: Mock() for k in (
            "Type", "Saved", "Collection", "Source", "Tags",
        )}
        state = SimpleNamespace(
            store=store, active_bin=lambda: "Work",
            copy_action=Mock(), pin_action=Mock(), delete_action=Mock(),
            preview_name=Mock(), preview_meta=preview_meta,
            preview_sub=Mock(), preview_label=Mock(), preview_stack=Mock(),
            preview_image=Mock(),
        )
        HistoryControllerMixin.preview_clip(state, current, None)
        state.preview_label.setText.assert_called_with(
            "Image dimensions exceed safe preview limits"
        )
        state.preview_image.show_image.assert_not_called()


if __name__ == "__main__":
    unittest.main()
