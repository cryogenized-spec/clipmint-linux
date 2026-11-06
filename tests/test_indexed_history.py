"""Fast full-body indexed search, metadata and safe migration tests."""
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time
import unittest

from clipmint.store import ClipStore
from clipmint.search_index import safe_fts_query

class IndexedHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / "legacy.sqlite3"
        self.db = ClipStore(self.path, max_unpinned=20000)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_full_text_beyond_preview_and_unicode(self):
        content = ("Invoice for a workshop. " * 100 + "rare diagnostic metallurgy endphrase").encode()
        ident = self.db.add("text", content, "Invoice summary")
        self.assertEqual([c.id for c in self.db.search("metallurgy")], [ident])
        self.assertEqual([c.id for c in self.db.search("diagnostic metallurgy")], [ident])
        self.assertEqual(self.db.search("notpresent"), [])
        self.assertEqual(self.db.search("metallurgy", "Personal"), [])
        self.assertIn("FTS5", self.db.index_status())

    def test_ranked_fts_is_scoped_to_selected_archive_bin(self):
        work = self.db.add("text", b"lucid beacons in full text", "Work note")
        personal = self.db.add("text", b"lucid beacons in full text", "Personal note", "Personal")
        self.assertEqual([c.id for c in self.db.search("lucid", "Work", "Best match")], [work])
        self.assertEqual([c.id for c in self.db.search("lucid", "Personal", "Best match")], [personal])

    def test_literal_specials_fts_grammar_never_executable(self):
        self.db.add("text", b"A_1%27", "A_1%27")
        self.db.add("text", b"other", "other")
        self.assertEqual(len(self.db.search("_")), 1)
        self.assertEqual(len(self.db.search("%")), 1)
        for query in ('" AND (', "foo OR *", "'; DROP TABLE clips;--"):
            self.db.search(query)
        self.assertEqual(self.db.count("Work"), 2)
        self.assertEqual(safe_fts_query(""), "")

    def test_pruning_removes_fts_records_and_tags(self):
        self.db.max_unpinned = 1
        original = self.db.add("text", b"rare prune token", "rare")
        self.db.set_tags(original, ["research"])
        newer = self.db.add("text", b"latest value", "latest")
        self.assertIsNone(self.db.get(original))
        self.assertEqual(self.db.search("prune"), [])
        self.assertEqual(self.db.all_tags(), [])
        self.assertEqual([c.id for c in self.db.search("latest")], [newer])
        self.db.delete(newer)
        self.assertEqual(self.db.search("latest"), [])

    def test_restart_indexes_legacy_and_metadata_survives(self):
        cid = self.db.add("text", b"invoice eighteen", "preview")
        self.db.favorite(cid, True)
        self.db.set_tags(cid, ["invoice", "customer"])
        tid = self.db.save_template("Dispatch", "Dear {{name}}, ready for collection.")
        self.db.close()
        self.db = ClipStore(self.path, max_unpinned=20000)
        self.assertEqual([c.id for c in self.db.search("eighteen")], [cid])
        self.assertEqual([c.id for c in self.db.search("", favorites_only=True)], [cid])
        self.assertEqual([c.id for c in self.db.search("", tag="invoice")], [cid])
        self.assertEqual(self.db.tags(cid), ["customer", "invoice"])
        self.assertEqual(self.db.templates()[0][:2], (tid, "Dispatch"))

    def test_fts_rebuild_existing_history_without_index(self):
        old = self.db.add("text", b"hidden actual body endpiece", "preview only")
        self.db.conn.execute("DELETE FROM clipmint_fts")
        self.db.conn.commit()
        self.db.close()
        self.db = ClipStore(self.path, max_unpinned=20000)
        self.assertEqual([c.id for c in self.db.search("endpiece")], [old])

    def test_favourites_are_not_pins_and_template_validation(self):
        cid = self.db.add("text", b"hello", "hello")
        self.db.favorite(cid, True)
        self.assertFalse(self.db.pinned(cid))
        self.assertTrue(self.db.is_favorite(cid))
        self.db.set_tags(cid, ["work", "WORK", "important"])
        self.assertEqual(self.db.tags(cid), ["important", "work"])
        with self.assertRaises(ValueError):
            self.db.set_tags(cid, ["has space"])
        with self.assertRaises(ValueError):
            self.db.save_template("Empty", "")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.save_template("Dispatch", "a")
            self.db.save_template("dispatch", "b")

    def test_category_filter_applies_before_result_limit(self):
        # Older URLs must not disappear behind the 1,000 latest plain-text
        # records. The same filter is shared with classify() to avoid drift.
        original_urls = [
            self.db.add("text", f"https://example.org/item/{i}".encode(),
                        f"https://example.org/item/{i}")
            for i in range(3)
        ]
        for i in range(1003):
            self.db.add("text", f"plain note number {i}".encode(),
                        f"plain note number {i}")
        self.assertEqual(
            [item.id for item in self.db.search(category="URLs")],
            list(reversed(original_urls)),
        )
        self.assertEqual(len(self.db.search(category="Text")), 1000)
        self.assertEqual(len(self.db.search(category="Images")), 0)

    def test_best_match_includes_older_exact_hit_after_1000_newer_results(self):
        if not self.db.search_index.enabled:
            self.skipTest("FTS5 unavailable")
        exact = self.db.add("text", b"greenhouse", "greenhouse", "Work")
        for i in range(1000):
            name = "Personal" if i % 2 else "Work"
            self.db.add(
                "text", f"greenhouse research note {i:04d}".encode(),
                f"Memo number {i:04d}", name,
            )
        matches = self.db.search("greenhouse", None, "Best match")
        self.assertEqual(len(matches), 1000)
        self.assertIn(exact, [entry.id for entry in matches])
        self.assertEqual(matches[0].id, exact)

    def test_index_search_large_corpus(self):
        for i in range(400):
            self.db.add("text", f"sample test document {i}".encode(), f"Entry {i}")
        cid = self.db.add("text", b"unique mystic foxglove term", "uncategorized")
        began = time.perf_counter()
        matches = self.db.search("foxglove", sort="Best match")
        elapsed = time.perf_counter() - began
        self.assertEqual([c.id for c in matches], [cid])
        self.assertLess(elapsed, 2.0)  # Generous bound for shared CI.

if __name__ == "__main__":
    unittest.main()
