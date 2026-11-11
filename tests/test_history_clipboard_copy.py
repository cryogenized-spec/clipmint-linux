"""Shared saved-history clipboard copy contracts across UI entry points."""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from clipmint.history_clipboard_copy import copy_saved_clip, CopyOutcome
from clipmint.history_controller import HistoryControllerMixin
from clipmint.hotkey_popup_controller import HotkeyPopupControllerMixin
from clipmint.window_actions import copy_clip


class CopySavedHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_missing_entry_never_accesses_guard_or_clipboard(self):
        store = SimpleNamespace(
            get=Mock(return_value=None),
            get_formats=Mock(),
            refresh_temporary_copy_time=Mock(),
        )
        guard, clipboard = Mock(), Mock()
        outcome = copy_saved_clip(store, guard, clipboard, 41)
        self.assertEqual(outcome, CopyOutcome.MISSING)
        guard.assert_not_called()
        clipboard.assert_not_called()
        store.get_formats.assert_not_called()
        store.refresh_temporary_copy_time.assert_not_called()

    def test_plain_rejects_image_without_side_effects(self):
        store = SimpleNamespace(
            get=Mock(return_value=("image", b"image bytes")),
            get_formats=Mock(),
            refresh_temporary_copy_time=Mock(),
        )
        guard, clipboard = Mock(), Mock()
        outcome = copy_saved_clip(store, guard, clipboard, 42, plain=True)
        self.assertEqual(outcome, CopyOutcome.TEXT_ONLY)
        guard.assert_not_called()
        clipboard.assert_not_called()
        store.get_formats.assert_not_called()
        store.refresh_temporary_copy_time.assert_not_called()

    def test_plain_copy_decodes_text_and_refreshes_temporary_clock(self):
        raw = "Emoji 🌿".encode("utf-8")
        store = SimpleNamespace(
            get=Mock(return_value=("text", raw)), get_formats=Mock(),
            refresh_temporary_copy_time=Mock(),
        )
        guard, clipboard = Mock(), Mock()
        result = copy_saved_clip(store, guard, clipboard, 11, plain=True)
        self.assertEqual(result, CopyOutcome.COPIED)
        guard.return_value.note_text.assert_called_once_with("Emoji 🌿")
        clipboard.return_value.setText.assert_called_once_with("Emoji 🌿")
        store.get_formats.assert_not_called()
        store.refresh_temporary_copy_time.assert_called_once_with(11)

    def test_rich_copy_preserves_html_and_mime_formats(self):
        raw = b"styled clipboard value"
        formats = {"text/html": b"<b>styled clipboard value</b>"}
        store = SimpleNamespace(
            get=Mock(return_value=("text", raw)),
            get_formats=Mock(return_value=formats),
            refresh_temporary_copy_time=Mock(),
        )
        guard = Mock()
        clipboard = Mock(return_value=QApplication.clipboard())
        try:
            outcome = copy_saved_clip(store, lambda: guard, clipboard, 14)
            self.assertEqual(outcome, CopyOutcome.COPIED)
            self.assertEqual(QApplication.clipboard().text(), "styled clipboard value")
            self.assertIn(
                "<b>styled clipboard value</b>", QApplication.clipboard().mimeData().html()
            )
            guard.note_entry.assert_called_once_with("text", raw)
            store.refresh_temporary_copy_time.assert_called_once_with(14)
        finally:
            QApplication.clipboard().clear()

    def test_mime_failure_never_marks_own_write_or_refreshes_ttl(self):
        store = SimpleNamespace(
            get=Mock(return_value=("text", b"value")),
            get_formats=Mock(return_value={}),
            refresh_temporary_copy_time=Mock(),
        )
        guard, clipboard = Mock(), Mock()
        with patch("clipmint.history_clipboard_copy.mime_from_entry",
                   side_effect=ValueError("corrupt MIME")):
            with self.assertRaisesRegex(ValueError, "corrupt MIME"):
                copy_saved_clip(store, guard, clipboard, 7)
        guard.assert_not_called()
        clipboard.assert_not_called()
        store.refresh_temporary_copy_time.assert_not_called()

    def test_window_copy_uses_shared_service_and_notifies_on_success_only(self):
        store = SimpleNamespace()
        item = SimpleNamespace(data=lambda role: 27)
        state = SimpleNamespace(store=store, inform=Mock())
        with patch("clipmint.window_actions.copy_saved_clip",
                   return_value=CopyOutcome.COPIED) as delegate:
            copy_clip(state, item)
        self.assertEqual(delegate.call_args.args[0], store)
        self.assertEqual(delegate.call_args.args[-1], 27)
        state.inform.assert_called_once()
        state.inform.reset_mock()
        with patch("clipmint.window_actions.copy_saved_clip",
                   return_value=CopyOutcome.MISSING):
            copy_clip(state, item)
        state.inform.assert_not_called()

    def test_history_queue_copy_uses_shared_service(self):
        state = SimpleNamespace(store=SimpleNamespace())
        with patch("clipmint.history_controller.copy_saved_clip",
                   return_value=CopyOutcome.COPIED) as service:
            self.assertTrue(HistoryControllerMixin._copy_entry_by_id(state, 29))
        self.assertEqual(service.call_args.args[-1], 29)

    def test_popup_plain_copy_remains_user_opt_in_for_auto_paste(self):
        state = SimpleNamespace(
            store=SimpleNamespace(), settings=SimpleNamespace(value=lambda *a, **k: False),
            _paste_to_target=Mock(),
        )
        with patch("clipmint.hotkey_popup_controller.copy_saved_clip",
                   return_value=CopyOutcome.COPIED) as service, \
             patch("clipmint.hotkey_popup_controller.QTimer") as timer:
            HotkeyPopupControllerMixin.quick_pick(state, 13, True, "0x42", "Firefox")
        self.assertEqual(service.call_args.args[-1], 13)
        self.assertTrue(service.call_args.kwargs["plain"])
        timer.singleShot.assert_not_called()
        state._paste_to_target.assert_not_called()


if __name__ == "__main__":
    unittest.main()
