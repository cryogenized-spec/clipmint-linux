"""Clipboard tabs filter content types; Autosort collections remain behind the scenes."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSettings
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QInputDialog

from clipmint.app import ClipMintWindow
from clipmint.history_filters import HISTORY_FILTERS, selected_category


class TimelineFiltersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.home = TemporaryDirectory()
        self.before = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = self.home.name
        config = str(Path(self.home.name) / "settings.ini")
        with patch("clipmint.app.QSettings",
                   side_effect=lambda *_: QSettings(
                       config, QSettings.Format.IniFormat
                   )):
            self.window = ClipMintWindow()
        self.window.monitoring = False

    def tearDown(self):
        w = self.window
        w.poller.stop()
        w._vault_lock_timer.stop()
        w._temporary_expiry_timer.stop()
        w._closing = True
        w.screenshot_notice.hide()
        if not w.store.closed:
            w.store.close()
        w.hide()
        w.deleteLater()
        self.app.processEvents()
        if self.before is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.before
        self.home.cleanup()

    def _select(self, label: str):
        index = next(
            i for i in range(self.window.tabs.count())
            if self.window.tabs.tabText(i) == label
        )
        self.window.tabs.setCurrentIndex(index)
        self.window.refresh()
        return [
            self.window.history.item(i).data(0x0100)
            for i in range(self.window.history.count())
        ]

    def test_top_tabs_are_type_filters_not_bins(self):
        w = self.window
        self.assertEqual(
            [w.tabs.tabText(i) for i in range(w.tabs.count())],
            [label for label, _category in HISTORY_FILTERS],
        )
        self.assertNotIn("Work", [w.tabs.tabText(i) for i in range(w.tabs.count())])
        self.assertNotIn("Writing", [w.tabs.tabText(i) for i in range(w.tabs.count())])
        self.assertIsNone(w.view_bin())
        self.assertEqual(selected_category(w.tabs), "All")
        self.assertEqual(w.bin_filter.currentText(), "All collections")

        w.store.add_bin("Writing")
        w.bin_filter.addItem("Writing", "Writing")
        entries = {
            "text": w.store.add("text", b"Ordinary useful workshop prose",
                                "Ordinary useful workshop prose", "Writing"),
            "link": w.store.add("text", b"https://example.org/article",
                                "https://example.org/article", "Personal"),
            "phone": w.store.add("text", b"+27 82 123 4567",
                                 "+27 82 123 4567", "Temporary"),
            "files": w.store.add("files", b"file:///tmp/clipmint-example.txt",
                                 "1 file(s): /tmp/clipmint-example.txt", "Work"),
        }
        image = QImage(12, 12, QImage.Format.Format_ARGB32)
        image.fill(QColor("#AE405B"))
        encoded = QByteArray()
        buffer = QBuffer(encoded)
        self.assertTrue(buffer.open(QIODevice.OpenModeFlag.WriteOnly))
        self.assertTrue(image.save(buffer, "PNG"))
        buffer.close()
        entries["image"] = w.store.add(
            "image", bytes(encoded), "Image 12 × 12", "Work"
        )
        self.assertTrue(all(isinstance(value, int) for value in entries.values()))
        self.assertEqual(len(self._select("All clips")), 5)
        self.assertEqual(self._select("Text"), [entries["text"]])
        self.assertEqual(self._select("Links"), [entries["link"]])
        self.assertEqual(self._select("Phone numbers"), [entries["phone"]])
        self.assertEqual(self._select("Images"), [entries["image"]])
        self.assertEqual(self._select("Files"), [entries["files"]])
        # A change of tab doesn't rewrite, move or remove stored items.
        self.assertEqual(
            w.store.conn.execute(
                "SELECT bin FROM clips WHERE id=?", (entries["text"],)
            ).fetchone()[0], "Writing"
        )

    def test_collection_scope_is_secondary_and_combines_with_tab_filter(self):
        w = self.window
        w.store.add_bin("Writing")
        w.bin_filter.addItem("Writing", "Writing")
        w.store.add("text", b"plain Work item", "plain Work item", "Work")
        w.store.add("text", b"plain Writing item", "plain Writing item", "Writing")
        w.store.add("text", b"https://example.org", "https://example.org", "Writing")
        self.assertEqual(len(self._select("Text")), 2)
        work_idx = w.bin_filter.findData("Work")
        w.bin_filter.setCurrentIndex(work_idx)
        self.assertEqual(len(self._select("Text")), 1)
        self.assertEqual(len(self._select("Links")), 0)
        writing_idx = w.bin_filter.findData("Writing")
        w.bin_filter.setCurrentIndex(writing_idx)
        self.assertEqual(len(self._select("Links")), 1)
        w.bin_filter.setCurrentIndex(0)
        self.assertEqual(len(self._select("All clips")), 3)

    def test_creating_collection_does_not_create_top_tab(self):
        w = self.window
        tab_count = w.tabs.count()
        with patch.object(QInputDialog, "getText", return_value=("Custom", True)):
            w.new_bin()
        self.assertEqual(w.tabs.count(), tab_count)
        self.assertEqual(w.bin_filter.currentData(), "Custom")
        self.assertIn("Custom", w.store.bins())


if __name__ == "__main__":
    unittest.main()
