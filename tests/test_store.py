from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from clipmint.store import ClipStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.store = ClipStore(Path(self.tmp.name) / "history.db", max_unpinned=2)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_add_retrieve_deduplicate(self):
        ident = self.store.add("text", b"hello", "hello")
        self.assertEqual(ident, self.store.add("text", b"hello", "hello"))
        self.assertEqual(self.store.get(ident), ("text", b"hello"))
        self.assertEqual(len(self.store.search()), 1)

    def test_pinning_prevents_pruning(self):
        ident = self.store.add("text", b"first", "first")
        self.store.pin(ident, True)
        for item in (b"second", b"third", b"fourth"):
            self.store.add("text", item, item.decode())
        self.assertTrue(self.store.pinned(ident))
        self.assertEqual(len(self.store.search()), 3)

    def test_literal_search_percent_underscore(self):
        self.store.add("text", b"A_1", "A_1")
        self.store.add("text", b"ABC", "ABC")
        self.assertEqual([x.preview for x in self.store.search("_")], ["A_1"])

    def test_delete(self):
        ident = self.store.add("text", b"gone", "gone")
        self.store.delete(ident)
        self.assertIsNone(self.store.get(ident))


if __name__ == "__main__":
    unittest.main()
