"""Bounded batch tag loading for fast archive and clipboard navigation."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from clipmint.store import ClipStore


class BulkTooltipTagTests(unittest.TestCase):
    def test_preserves_tags_order_and_returns_empty_for_unlabeled_entries(self):
        with TemporaryDirectory() as directory:
            store = ClipStore(Path(directory) / "history.sqlite3")
            try:
                tagged = store.add("text", b"tagged fixture", "Tagged")
                plain = store.add("text", b"untagged fixture", "Untagged")
                store.set_tags(tagged, ["zulu", "alpha", "beta"])
                self.assertEqual(
                    store.tags_for_ids([plain, tagged, tagged]),
                    {tagged: ["alpha", "beta", "zulu"]},
                )
                self.assertEqual(store.tags_for_ids([]), {})
                self.assertEqual(store.tags_for_ids([999_999]), {})
            finally:
                store.close()

    def test_500_visible_entries_use_two_bounded_queries_not_500(self):
        with TemporaryDirectory() as directory:
            store = ClipStore(
                Path(directory) / "history.sqlite3", max_unpinned=600,
            )
            try:
                ids = []
                for i in range(500):
                    ident = store.add(
                        "text", f"synthetic tag fixture {i}".encode(),
                        f"Synthetic {i}",
                    )
                    ids.append(ident)
                for ident in (ids[0], ids[420]):
                    store.set_tags(ident, ["reviewed"])
                statements = []
                store.conn.set_trace_callback(statements.append)
                try:
                    results = store.tags_for_ids(ids)
                finally:
                    store.conn.set_trace_callback(None)
                lookups = [
                    statement for statement in statements
                    if "FROM clip_tags" in statement
                ]
                self.assertEqual(len(lookups), 2)
                self.assertEqual(results[ids[0]], ["reviewed"])
                self.assertEqual(results[ids[420]], ["reviewed"])
                self.assertNotIn(ids[1], results)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
