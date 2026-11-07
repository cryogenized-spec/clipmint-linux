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
from clipmint.smart_types import DEFAULT_BINS as SMART_BINS, default_smart_rules


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

    def test_plaintext_fts_finds_older_filtered_full_body_match(self):
        """Filtered search must not discard an older FTS-only match."""
        with TemporaryDirectory() as root:
            store = ClipStore(Path(root) / "history.sqlite3", max_unpinned=1100)
            try:
                store.add_bin("Writing")
                old_id = store.add(
                    "text",
                    b"old writing excerpt holding farawaymatch in its body",
                    "Old writing excerpt", "Writing",
                )
                self.assertIsNotNone(old_id)
                store.favorite(old_id, True)
                store.set_tags(old_id, ["important"])
                for index in range(1000):
                    text = f"farawaymatch record number {index:04d}"
                    self.assertIsNotNone(store.add(
                        "text", text.encode(), text, "Work"
                    ))
                self.assertEqual(store.count(None), 1001)
                self.assertEqual(
                    [clip.id for clip in store.search(
                        "farawaymatch", None, favorites_only=True
                    )],
                    [old_id],
                )
                self.assertEqual(
                    [clip.id for clip in store.search(
                        "farawaymatch", None, tag="important", category="Text"
                    )],
                    [old_id],
                )
                self.assertEqual(
                    [clip.id for clip in store.search(
                        "farawaymatch", None, sort="Best match",
                        favorites_only=True,
                    )],
                    [old_id],
                )
                self.assertEqual(store.search("farawaymatch", "Personal"), [])
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

    def test_plain_fts_filters_before_global_candidate_limit(self):
        """A favoured old full-body match must survive 1,000 newer FTS hits."""
        with TemporaryDirectory() as root:
            store = ClipStore(Path(root) / "history.sqlite3")
            try:
                if not store.search_index.enabled:
                    self.skipTest("FTS5 not installed")
                store.add_bin("Writing")
                store.add_bin("Utility")
                oldest = store.add(
                    "text", b"greenhouse previously clipped from Firefox",
                    "Old favourite note", "Writing",
                )
                store.favorite(oldest, True)
                store.set_tags(oldest, ["keeper"])
                bins = ("Work", "Personal", "Temporary", "Writing", "Utility")
                for number in range(1000):
                    # Term is deliberately absent from preview, requiring
                    # the full-body FTS index instead of substring fallback.
                    phrase = f"greenhouse document number {number:04d}".encode()
                    preview = f"Memo {number:04d}"
                    store.add("text", phrase, preview, bins[number % len(bins)])
                self.assertEqual(store.count(None), 1001)
                self.assertEqual(
                    [clip.id for clip in store.search(
                        "greenhouse", None, favorites_only=True
                    )],
                    [oldest],
                )
                self.assertEqual(
                    [clip.id for clip in store.search(
                        "greenhouse", None, tag="keeper"
                    )],
                    [oldest],
                )
                self.assertEqual(
                    [clip.id for clip in store.search(
                        "greenhouse", "Writing", favorites_only=True
                    )],
                    [oldest],
                )
            finally:
                store.close()

    def test_encrypted_combined_search_finds_older_matches_after_1000_clips(self):
        """The result cap applies to matched clips, not ciphertext scanned."""
        with TemporaryDirectory() as root:
            store = EncryptedClipStore(
                Path(root) / "secure-history.sqlite3",
                bytes(range(32)), max_unpinned=1200,
            )
            try:
                store.add_bin("Writing")
                old_id = store.add(
                    "text", b"archived greenhouse memories",
                    "archived greenhouse memories", "Writing",
                )
                self.assertIsNotNone(old_id)
                for number in range(1000):
                    value = f"unrelated office memo record {number:04d}"
                    self.assertIsNotNone(store.add(
                        "text", value.encode(), value, "Work"
                    ))
                self.assertEqual(store.count(None), 1001)
                # A combined encrypted scan must never sort entire screenshot
                # ciphertext blobs in a temporary SQLite B-tree. The global
                # recency index supplies both forward and reverse traversal.
                for direction in ("DESC", "ASC"):
                    plan = " ".join(
                        str(row[3]) for row in store.conn.execute(
                            "EXPLAIN QUERY PLAN SELECT id,kind,content,pinned,"
                            "created_at,bin,favorite,touch_seq FROM clips "
                            "WHERE corrupt=0 ORDER BY touch_seq " +
                            direction + ",id " + direction
                        )
                    )
                    self.assertNotIn("USE TEMP B-TREE", plan)
                    self.assertIn("idx_clips_global_recent", plan)
                self.assertEqual(len(store.search("", None)), 1000)
                self.assertEqual(
                    [clip.id for clip in store.search("archived greenhouse", None)],
                    [old_id],
                )
                self.assertEqual(
                    store.search("", None, sort="Oldest first")[0].id,
                    old_id,
                )
                store.favorite(old_id, True)
                self.assertEqual(
                    [clip.id for clip in store.search(
                        "", None, favorites_only=True
                    )],
                    [old_id],
                )
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
                self.assertEqual(window.tabs.tabText(1), "Text")
                self.assertEqual(window.tabs.tabText(2), "Links")
                self.assertEqual(window.tabs.currentIndex(), 0)
                self.assertIsNone(window.view_bin())
                self.assertEqual(window.bin_filter.currentText(), "All collections")
                self.assertEqual(window.active_bin(), "Work")
                # Other UI tests may have persisted an older five-rule
                # Autosort preference. Explicitly configure the default
                # thirty-rule scenario instead of depending on Qt's shared
                # Settings path/cached native format across the whole suite.
                for bin_name in SMART_BINS:
                    if bin_name not in window.store.bins():
                        window.store.add_bin(bin_name)
                        window.bin_filter.addItem(bin_name, bin_name)
                window.autosort_rules = default_smart_rules()
                window.autosort_enabled = True

                with patch("clipmint.app.blocked_foreground", return_value=False):
                    self.app.clipboard().setText(
                        "A normal note about sunshine and window curtains"
                    )
                    # Qt/offscreen backends differ in whether setText
                    # synchronously emits dataChanged.
                    window.clipboard_changed()
                self.app.processEvents()
                self.assertEqual(window.store.count("Writing"), 1)
                self.assertEqual(window.store.count("Work"), 0)
                self.assertEqual(window.store.count(None), 1)
                self.assertEqual(window.history.count(), 1)
                # The unified stream must not decorate actual clip content
                # with storage-bin labels or type tags.
                self.assertEqual(
                    window.history.item(0).text(),
                    "A normal note about sunshine and window curtains",
                )
                metadata = window.history.item(0).data(
                    Qt.ItemDataRole.UserRole + 1
                )
                self.assertEqual(metadata["bin"], "Writing")
                # Context menus must offer Work for a Writing clip, even
                # though Work is the default write destination in All clips.
                destinations = window.move_destinations_for_item(
                    window.history.item(0)
                )
                self.assertIn("Work", destinations)
                self.assertNotIn("Writing", destinations)

                # Top tabs are content filters, not a physical collection.
                self.assertNotIn(
                    "Writing",
                    [window.tabs.tabText(i) for i in range(window.tabs.count())],
                )
                text_index = next(
                    i for i in range(window.tabs.count())
                    if window.tabs.tabText(i) == "Text"
                )
                window.tabs.setCurrentIndex(text_index)
                self.assertEqual(window.history.count(), 1)
                links_index = next(
                    i for i in range(window.tabs.count())
                    if window.tabs.tabText(i) == "Links"
                )
                window.tabs.setCurrentIndex(links_index)
                self.assertEqual(window.history.count(), 0)
                window.tabs.setCurrentIndex(0)
                work_index = window.bin_filter.findData("Work")
                window.bin_filter.setCurrentIndex(work_index)
                self.assertEqual(window.history.count(), 0)
                writing_index = window.bin_filter.findData("Writing")
                window.bin_filter.setCurrentIndex(writing_index)
                self.assertEqual(window.history.count(), 1)
                window.bin_filter.setCurrentIndex(0)
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
