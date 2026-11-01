"""Bins, sort orders and historical database migration."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from clipmint.store import ClipStore, Clip, classify, looks_sensitive
from clipmint.capture import RegionRecorder


class BinTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "clips.db"
        self.db = ClipStore(self.path, max_unpinned=2)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_bins_are_isolated_and_sort_latest_default(self):
        w1 = self.db.add("text", b"zzz", "zzz", "Work")
        self.db.add("text", b"aaa", "aaa", "Personal")
        w2 = self.db.add("text", b"bbb", "bbb", "Work")
        self.assertEqual([c.id for c in self.db.search(bin_name="Work")], [w2, w1])
        self.assertEqual([c.preview for c in self.db.search(bin_name="Personal")], ["aaa"])
        self.assertEqual([c.preview for c in self.db.search(bin_name="Work",sort="A–Z")], ["bbb", "zzz"])
        self.assertEqual([c.id for c in self.db.search(bin_name="Work",sort="Oldest first")], [w1, w2])
        self.assertEqual(len(self.db.search(bin_name="Work",sort="Numbered list")), 2)

    def test_moving_and_pruning_are_per_bin(self):
        one = self.db.add("text", b"old", "old")
        self.db.move(one, "Temporary")
        for word in ("two","three","four"):
            self.db.add("text", word.encode(), word, "Work")
        self.assertEqual([c.preview for c in self.db.search(bin_name="Temporary")], ["old"])
        self.assertEqual([c.preview for c in self.db.search(bin_name="Work")], ["four","three"])

    def test_categories_and_secret_skip(self):
        clips = [
            Clip(1,"text","https://example.com",False,""),
            Clip(2,"text","+27 83 123 4567",False,""),
            Clip(3,"image","Image 100 x 100",False,""),
            Clip(4,"text","Meeting notes",False,""),
        ]
        self.assertEqual([classify(c) for c in clips], ["URLs","Phone numbers","Images","Text"])
        self.assertTrue(looks_sensitive("password=foobar"))
        self.assertTrue(looks_sensitive("api_key: abc123"))
        self.assertFalse(looks_sensitive("ordinary clipboard text"))

    def test_migrates_old_history(self):
        self.db.close()
        self.path.unlink()
        db = sqlite3.connect(self.path)
        db.execute("""CREATE TABLE clips (
             id INTEGER PRIMARY KEY, kind TEXT NOT NULL, content BLOB NOT NULL,
             preview TEXT NOT NULL, pinned INTEGER NOT NULL DEFAULT 0,
             created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("INSERT INTO clips(kind,content,preview) VALUES('text',?,?)",(b"saved","saved"))
        db.commit()
        db.close()
        self.db = ClipStore(self.path)
        self.assertEqual([c.preview for c in self.db.search(bin_name="Work")], ["saved"])

    def test_discard_pending_capture(self):
        pending = Path(self.temp.name) / ".pending-test.mp4"
        logfile = pending.with_suffix(".ffmpeg.log")
        pending.write_bytes(b"dummy")
        logfile.write_text("dummy")
        self.assertIsNone(RegionRecorder.resolve(pending, False))
        self.assertFalse(pending.exists())
        self.assertFalse(logfile.exists())


if __name__ == "__main__":
    unittest.main()
