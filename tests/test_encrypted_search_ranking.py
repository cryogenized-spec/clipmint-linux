"""Encrypted search ranking stays in memory and never indexes plaintext."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from nacl.secret import SecretBox
from nacl.utils import random

from clipmint.secure_history import EncryptedClipStore


class EncryptedSearchRankingTests(unittest.TestCase):
    def test_active_crimson_archive_search_uses_debounce(self):
        source = (Path(__file__).resolve().parents[1] /
                  "clipmint" / "crimson_ui.py").read_text(encoding="utf-8")
        self.assertIn(
            "w.search.textChanged.connect(w._schedule_history_search)", source
        )
        self.assertNotIn("w.search.textChanged.connect(w.refresh)", source)

    def test_best_match_ranks_exact_then_prefix_then_substring(self):
        with TemporaryDirectory() as home:
            store = EncryptedClipStore(
                Path(home) / "secure-history.sqlite3",
                random(SecretBox.KEY_SIZE),
            )
            try:
                exact = store.add("text", b"alpha", "alpha")
                prefix = store.add("text", b"alpha checklist", "Alpha checklist")
                substring = store.add("text", b"review alpha report", "Review Alpha report")
                self.assertEqual(
                    [item.id for item in store.search("alpha", sort="Latest first")],
                    [substring, prefix, exact],
                )
                self.assertEqual(
                    [item.id for item in store.search("alpha", sort="Best match")],
                    [exact, prefix, substring],
                )
                self.assertFalse(store.search_index.enabled)
                self.assertIsNone(store.conn.execute(
                    "SELECT name FROM sqlite_master WHERE name='clipmint_fts'"
                ).fetchone())
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
