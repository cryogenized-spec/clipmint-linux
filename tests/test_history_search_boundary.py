"""Protect the model/store/search import boundaries without changing data."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from clipmint.clip_model import Clip as ModelClip, SORTS as ModelSorts
from clipmint.history_search import HistorySearchService
from clipmint.store import Clip, ClipStore, SORTS
from clipmint.secure_history import EncryptedClipStore


class HistorySearchBoundaryTests(unittest.TestCase):
    def test_existing_store_exports_keep_identity(self):
        self.assertIs(Clip, ModelClip)
        self.assertIs(SORTS, ModelSorts)
        self.assertFalse(issubclass(ClipStore, HistorySearchService))
        self.assertTrue(issubclass(EncryptedClipStore, ClipStore))
        self.assertIsNot(EncryptedClipStore.search, ClipStore.search)

    def test_ordinary_search_and_filters_still_use_metadata_only(self):
        with TemporaryDirectory() as directory:
            store = ClipStore(Path(directory) / "history.sqlite3")
            try:
                self.assertIsInstance(store._history_search, HistorySearchService)
                self.assertIs(store._history_search.conn, store.conn)
                self.assertIs(store._history_search.search_index, store.search_index)
                work = store.add("text", b"laser etching details", "Workshop", "Work")
                personal = store.add("text", b"laser etching details", "Private", "Personal")
                store.favorite(personal, True)
                self.assertEqual(
                    [clip.id for clip in store.search("etching", bin_name=None)],
                    [personal, work],
                )
                self.assertEqual(
                    [clip.id for clip in store.search("etching", bin_name="Work")],
                    [work],
                )
                self.assertEqual(
                    [clip.id for clip in store.search(
                        "etching", bin_name=None, favorites_only=True
                    )],
                    [personal],
                )
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
