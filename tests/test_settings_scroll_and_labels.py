"""Regression tests: scrolling Settings cannot initiate history deletion.

The optional labels setting is a display-only choice, off by default.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import QPoint, QPointF, Qt, QSettings
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from clipmint.app import ClipMintWindow


class ScrollAndLabelsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.previous_data = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = self.temp.name
        settings_file = str(Path(self.temp.name) / "settings.ini")
        with patch(
            "clipmint.app.QSettings",
            side_effect=lambda *_: QSettings(settings_file, QSettings.Format.IniFormat),
        ):
            self.window = ClipMintWindow()

    def tearDown(self):
        window = self.window
        window._hidden_clipboard_timer.stop()
        window.poller.stop()
        window._vault_lock_timer.stop()
        window._temporary_expiry_timer.stop()
        window._closing = True
        window.screenshot_notice.hide()
        if not window.store.closed:
            window.store.close()
        window.hide()
        window.deleteLater()
        self.app.processEvents()
        if self.previous_data is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.previous_data
        self.temp.cleanup()

    def test_mouse_wheel_over_storage_selector_does_not_raise_pruning_prompt(self):
        w = self.window
        selector = w.history_storage_limit
        self.assertEqual(selector.currentData(), 0)
        self.assertEqual(w.settings.value("history/max_total_mb", 0, type=int), 0)
        with patch.object(QMessageBox, "question") as confirm, \
             patch.object(w.store, "prune_storage_bytes") as prune:
            for delta in (-120, 120, -120, -120):
                event = QWheelEvent(
                    QPointF(8, 8), QPointF(8, 8),
                    QPoint(0, 0), QPoint(0, delta),
                    Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier,
                    Qt.ScrollPhase.ScrollUpdate, False,
                )
                self.app.sendEvent(selector, event)
                self.assertFalse(event.isAccepted())
            self.app.processEvents()
            self.assertEqual(selector.currentData(), 0)
            self.assertEqual(w.settings.value("history/max_total_mb", 0, type=int), 0)
            confirm.assert_not_called()
            prune.assert_not_called()

    def test_click_selection_still_requires_explicit_confirmation(self):
        w = self.window
        selector = w.history_storage_limit
        with patch.object(
            QMessageBox, "question",
            return_value=QMessageBox.StandardButton.No
        ) as confirm, patch.object(w.store, "prune_storage_bytes") as prune:
            selector.setCurrentIndex(selector.findData(512))
            confirm.assert_called_once()
            prune.assert_not_called()
            self.assertEqual(selector.currentData(), 0)
            self.assertEqual(w.settings.value("history/max_total_mb", 0, type=int), 0)
        with patch.object(
            QMessageBox, "question",
            return_value=QMessageBox.StandardButton.Yes
        ) as confirm, patch.object(
            w.store, "prune_storage_bytes", return_value=0
        ) as prune:
            selector.setCurrentIndex(selector.findData(512))
            confirm.assert_called_once()
            prune.assert_called_once()
            self.assertEqual(selector.currentData(), 512)
            self.assertEqual(w.store.max_total_bytes, 512 * 1024 * 1024)
            self.assertEqual(w.settings.value("history/max_total_mb", 0, type=int), 512)

    def test_all_clips_labels_off_by_default_and_opt_in_without_data_mutation(self):
        w = self.window
        self.assertFalse(w.clip_labels_toggle.isChecked())
        self.assertEqual(
            w.settings.value("history/show_clip_labels", False, type=bool), False
        )
        ident = w.store.add(
            "text", b"Plain workshop clipboard item",
            "Plain workshop clipboard item", "Work"
        )
        self.assertIsNotNone(ident)
        w.refresh()
        self.assertEqual(w.history.count(), 1)
        item = w.history.item(0)
        self.assertEqual(item.text(), "Plain workshop clipboard item")
        self.assertFalse(item.data(int(Qt.ItemDataRole.UserRole) + 1)["show_badges"])

        w.clip_labels_toggle.setChecked(True)
        item = w.history.item(0)
        self.assertEqual(item.text(), "[Work]  Plain workshop clipboard item")
        self.assertTrue(item.data(int(Qt.ItemDataRole.UserRole) + 1)["show_badges"])
        self.assertTrue(w.settings.value("history/show_clip_labels", False, type=bool))

        w.tabs.setCurrentIndex(1)  # Text filter: tags are only optional in All clips
        item = w.history.item(0)
        self.assertEqual(item.text(), "Plain workshop clipboard item")
        self.assertFalse(item.data(int(Qt.ItemDataRole.UserRole) + 1)["show_badges"])

        w.tabs.setCurrentIndex(0)
        w.clip_labels_toggle.setChecked(False)
        self.assertEqual(w.history.item(0).text(), "Plain workshop clipboard item")
        self.assertFalse(
            w.history.item(0).data(int(Qt.ItemDataRole.UserRole) + 1)["show_badges"]
        )
        self.assertEqual(w.store.get(ident), ("text", b"Plain workshop clipboard item"))


if __name__ == "__main__":
    unittest.main()
