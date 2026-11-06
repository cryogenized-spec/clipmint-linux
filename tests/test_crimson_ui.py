"""Crimson Archive visual composition and functionality regression checks."""
import os
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
from clipmint.app import ClipMintWindow


class CrimsonArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self):
        self._temp = TemporaryDirectory()
        self._prior = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = self._temp.name
        window = ClipMintWindow()
        return window

    def finish_window(self, w):
        w.store.close()
        w.close()
        w.deleteLater()
        self.app.processEvents()
        if self._prior is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self._prior
        self._temp.cleanup()

    def test_approved_four_column_composition_and_complete_character(self):
        window = self.make_window()
        try:
            window.resize(1360, 900)
            window.show()
            self.app.processEvents()
            self.assertTrue(window.manga_dock.isVisible())
            self.assertGreaterEqual(window.manga_dock.width(), 305)
            self.assertGreaterEqual(window.manga_mascot.width(), 180)
            self.assertGreaterEqual(window.manga_mascot.height(), 230)
            self.assertFalse(window.manga_mascot.portrait.isNull())
            self.assertTrue(window.preview_panel.isVisible())
            self.assertTrue(window.dock_panel.isVisible())
            self.assertTrue(window.nav_buttons["Clipboard"].isChecked())
            self.assertEqual(window.kana_tag.text(), "クリップミント")
            self.assertIn("プレビュー", window.preview_heading.text())
            self.assertIn("琥珀", window.maid_caption.text())
            self.assertEqual(window.screenshot_button.objectName(), "screenshot")
            self.assertIn("泡沫", window.kohaku_japanese.text())
            self.assertIn("Utakata", window.kohaku_roman.text())
            self.assertIn("Transient thoughts", window.kohaku_english.text())
            self.assertIn("Clipboard", window.nav_buttons["Clipboard"].text())
            bilingual = {
                "Clipboard": ("Clipboard", "クリップボード"),
                "Screenshots": ("Screenshots", "撮影画像"),
                "Recordings": ("Recordings", "画面録画"),
                "Secrets & Variables": ("Vault", "秘密保管庫"),
                "Autosort": ("Autosort", "自動仕分け"),
                "Settings": ("Settings", "設定"),
            }
            for section, (english, japanese) in bilingual.items():
                button = window.nav_buttons[section]
                self.assertIn(english, button.text())
                self.assertIn(japanese, button.text())
                self.assertEqual(button.property("dockSubtitle"), japanese)
            self.assertEqual(window.record_button.objectName(), "record")
            for child in (window.manga_dock, window.pages, window.preview_panel, window.dock_panel):
                self.assertGreater(child.height(), 500)
        finally:
            self.finish_window(window)

    def test_reference_typography_palette_and_working_controls(self):
        """The visual overhaul keeps native Qt actions and accessible focus."""
        window = self.make_window()
        try:
            window.resize(1507, 1044)
            window.show()
            self.app.processEvents()
            stylesheet = window.styleSheet()
            self.assertIn("Cormorant Garamond", stylesheet)
            self.assertIn("#C48C6B", stylesheet)
            self.assertIn("qlineargradient", stylesheet)
            self.assertIn("SYSTEM READY", window.findChildren(
                type(window.kana_tag), "systemReady")[0].text())
            self.assertGreaterEqual(window.record_button.minimumHeight(), 60)
            self.assertGreaterEqual(window.screenshot_button.minimumHeight(), 60)
            self.assertIsNotNone(window.record_menu.menu())
            self.assertIsNotNone(window.screenshot_menu.menu())
            self.assertTrue(window.copy_action.isEnabled() or not window.history.count())
            self.assertFalse(window.wordmark.grab().isNull())
            self.assertFalse(window.record_button.grab().isNull())
        finally:
            self.finish_window(window)

    def test_compact_view_preserves_data_and_navigation(self):
        window = self.make_window()
        try:
            window.resize(900, 650)
            window.show()
            self.app.processEvents()
            self.assertTrue(window.manga_dock.isHidden())
            self.assertTrue(window.pages.isVisible())
            self.assertTrue(window.preview_panel.isVisible())
            window.open_section(1)
            self.app.processEvents()
            self.assertTrue(window.nav_buttons["Screenshots"].isChecked())
            self.assertTrue(window.preview_panel.isHidden())
            window.open_section(0)
            self.app.processEvents()
            self.assertTrue(window.preview_panel.isVisible())
        finally:
            self.finish_window(window)

    def test_live_rows_copy_pin_move_search_and_delete(self):
        window = self.make_window()
        try:
            window.show()
            self.app.processEvents()
            # Source scope is now secondary to the top content-type tabs.
            work_index = window.bin_filter.findData("Work")
            self.assertGreater(work_index, 0)
            window.bin_filter.setCurrentIndex(work_index)
            a = window.store.add("text", b"inspect brass", "inspect brass", "Work")
            window.store.add("text", b"https://example.org", "https://example.org", "Work")
            window.store.add("text", b"personal note", "personal note", "Personal")
            window.refresh()
            self.assertEqual(window.history.count(), 2)
            item = next(window.history.item(i) for i in range(window.history.count())
                        if window.history.item(i).data(Qt.ItemDataRole.UserRole) == a)
            window.history.setCurrentItem(item)
            self.app.processEvents()
            self.assertIn("inspect brass", window.preview_label.text())
            self.assertEqual(window.preview_meta["Collection"].text(), "Work")
            self.assertEqual(window.preview_meta["Source"].text(), "Clipboard text")
            window.copy_selected()
            self.assertEqual(QApplication.clipboard().text(), "inspect brass")
            window.toggle_pin_selected()
            self.assertTrue(window.store.pinned(a))
            self.assertEqual(window.pin_action.text(), "UNPIN")
            # This assertion tests delayed search repaint, not asynchronous
            # background clipboard ingestion during the Qt event-loop wait.
            window.monitoring = False
            window.search.setText("non-matching")
            self.assertTrue(window._history_search_timer.isActive())
            QTest.qWait(220)  # Searches are now intentionally debounced.
            self.assertEqual(window.history.count(), 0)
            self.assertFalse(window.copy_action.isEnabled())
            window.search.clear()
            QTest.qWait(220)
            self.assertEqual(window.history.count(), 2)
            window.history.setCurrentRow(0)
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
                window.delete_selected()
            self.assertEqual(window.history.count(), 2)
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                window.delete_selected()
            self.assertEqual(window.history.count(), 1)
        finally:
            self.finish_window(window)


if __name__ == "__main__":
    unittest.main()
