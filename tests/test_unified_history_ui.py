"""Regression tests for all-collections clipboard visibility.

Autosort routes ordinary Firefox text to Writing, not the Work collection.
The initial Clipboard view must show the clip even when routed elsewhere.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from clipmint.app import ClipMintWindow
from clipmint.store import ClipStore
from clipmint.secure_history import EncryptedClipStore


class AllCollectionsDatabaseTests(unittest.TestCase):
    def test_plain_history_can_search_and_count_across_bins(self):
        with TemporaryDirectory() as root:
            store = ClipStore(Path(root) / "history.sqlite3")
            try:
                store.add_bin("Writing")
                store.add("text", b"alpha greenhouse phrase", "alpha greenhouse phrase", "Work")
                store.add(
                    "text", b"ordinary sentence with a farawayuniquegardenword",
                    "ordinary sentence", "Writing",
                )
                self.assertEqual(store.count("Work"), 1)
                self.assertEqual(store.count("Writing"), 1)
                self.assertEqual(store.count(None), 2)
                self.assertEqual(len(store.search("", None)), 2)
                self.assertEqual(store.search("", None)[0].bin, "Writing")
                self.assertEqual(
                    [v.bin for v in store.search("farawayuniquegardenword", None)],
                    ["Writing"],
                )
                self.assertEqual(store.search("farawayuniquegardenword", "Work"), [])
                self.assertEqual(
                    [v.bin for v in store.search("", None, category="Text")],
                    ["Writing", "Work"],
                )
            finally:
                store.close()

    def test_encrypted_history_combines_bins_without_plaintext_index(self):
        with TemporaryDirectory() as root:
            store = EncryptedClipStore(Path(root) / "secure-history.sqlite3", bytes(range(32)))
            try:
                store.add_bin("Writing")
                store.add("text", b"clipboard paper sample", "clipboard paper sample", "Work")
                store.add("text", b"fresh normal Firefox copy",
                          "fresh normal Firefox copy", "Writing")
                self.assertEqual(store.count(None), 2)
                self.assertEqual(
                    [entry.bin for entry in store.search("", None)],
                    ["Writing", "Work"],
                )
                self.assertEqual(
                    [entry.bin for entry in store.search("Firefox", None)],
                    ["Writing"],
                )
                self.assertEqual(store.search("Firefox", "Work"), [])
                self.assertFalse(store.search_index.enabled)
            finally:
                store.close()


class VisibleHistoryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_normal_browser_text_visible_in_default_main_history(self):
        with TemporaryDirectory() as root:
            previous = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            QSettings.setDefaultFormat(QSettings.Format.IniFormat)
            QSettings.setPath(QSettings.Format.IniFormat,
                              QSettings.Scope.UserScope, root)
            window = None
            try:
                window = ClipMintWindow()
                self.assertEqual(window.tabs.tabText(0), "All clips")
                self.assertEqual(window.tabs.currentIndex(), 0)
                self.assertIsNone(window.view_bin())
                self.assertEqual(window.active_bin(), "Work")
                self.assertTrue(window.autosort_enabled)

                with patch("clipmint.app.blocked_foreground", return_value=False):
                    self.app.clipboard().setText(
                        "A normal note about sunshine and window curtains"
                    )
                    # Qt/offscreen backends differ in whether setText
                    # synchronously emits dataChanged.
                    window.clipboard_changed()
                self.app.processEvents()
                self.assertEqual(
                    window.store.count("Writing"), 1,
                    "capture diagnostics: " + repr({
                        "monitoring": window.monitoring,
                        "security_error": window.history_security_error,
                        "autosort_enabled": window.autosort_enabled,
                        "autosort_rules": len(window.autosort_rules),
                        "counts": {name: window.store.count(name)
                                   for name in window.store.bins()},
                        "clipboard_has_text": self.app.clipboard().mimeData().hasText(),
                        "clipboard_text": self.app.clipboard().text()[:80],
                    }),
                )
                self.assertEqual(window.store.count("Work"), 0)
                self.assertEqual(window.store.count(None), 1)
                self.assertEqual(window.history.count(), 1)
                self.assertIn("[Writing]", window.history.item(0).text())
                # Context menus must offer Work for a Writing clip, even
                # though Work is the default write destination in All clips.
                destinations = window.move_destinations_for_item(
                    window.history.item(0)
                )
                self.assertIn("Work", destinations)
                self.assertNotIn("Writing", destinations)

                work_index = next(
                    i for i in range(window.tabs.count())
                    if window.tabs.tabText(i) == "Work"
                )
                window.tabs.setCurrentIndex(work_index)
                self.assertEqual(window.history.count(), 0)
                writing_index = next(
                    i for i in range(window.tabs.count())
                    if window.tabs.tabText(i) == "Writing"
                )
                window.tabs.setCurrentIndex(writing_index)
                self.assertEqual(window.history.count(), 1)
                window.tabs.setCurrentIndex(0)
                self.assertEqual(window.history.count(), 1)
            finally:
                if window is not None:
                    window.poller.stop()
                    window._vault_lock_timer.stop()
                    window.store.close()
                    window.screenshot_notice.hide()
                    window.hide()
                if previous is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = previous

    def test_all_clips_view_cannot_be_written_as_a_physical_bin(self):
        with TemporaryDirectory() as root:
            store = ClipStore(Path(root) / "history.sqlite3")
            try:
                self.assertNotIn("All clips", store.bins())
                with self.assertRaisesRegex(ValueError, "Unknown"):
                    store.add("text", b"nonsecret example", "nonsecret example",
                              "All clips")
                self.assertEqual(store.count(None), 0)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
