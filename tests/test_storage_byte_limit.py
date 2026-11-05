"""Opt-in byte retention does not erase pinned clips or upgrade history."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from clipmint.store import ClipStore


class StorageByteLimitTests(unittest.TestCase):
    def test_default_off_and_no_startup_eviction(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "history.sqlite3"
            db = ClipStore(path, max_unpinned=100)
            original = db.add("image", b"Z" * 200, "Image")
            db.close()
            db = ClipStore(path, max_unpinned=100)
            try:
                self.assertIsNone(db.max_total_bytes)
                self.assertEqual(db.get(original)[1], b"Z" * 200)
            finally:
                db.close()

    def test_byte_cap_evicts_oldest_unpinned_across_bins(self):
        with TemporaryDirectory() as root:
            db = ClipStore(Path(root) / "history.sqlite3",
                           max_unpinned=100, max_total_bytes=115)
            try:
                older = db.add("image", b"X" * 60, "Old", "Work")
                newer = db.add("image", b"Y" * 60, "New", "Personal")
                self.assertIsNone(db.get(older))
                self.assertIsNotNone(db.get(newer))
                self.assertLessEqual(db.payload_bytes(), 115)
            finally:
                db.close()

    def test_pins_survive_even_when_alone_over_limit(self):
        with TemporaryDirectory() as root:
            db = ClipStore(Path(root) / "history.sqlite3", max_unpinned=100)
            try:
                keep = db.add("image", b"A" * 200, "Pinned")
                db.pin(keep, True)
                db.max_total_bytes = 100
                self.assertEqual(db.prune_storage_bytes(), 0)
                self.assertEqual(db.get(keep)[1], b"A" * 200)
                ignored = db.add("image", b"B" * 40, "New")
                self.assertIsNone(ignored)
                self.assertEqual(db.count("Work"), 1)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
