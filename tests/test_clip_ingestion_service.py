"""Explicit capture dependencies and live-store migration coverage."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from clipmint.clip_ingestion import ClipboardIngestionService, IngestionResult
from clipmint.clipboard_formats import ClipboardEntry
from clipmint.app import ClipMintWindow


class ClipIngestionServiceTests(unittest.TestCase):
    def setUp(self):
        self.original = SimpleNamespace(
            add=Mock(return_value=19), tags=Mock(return_value=[]),
            set_tags=Mock(),
        )
        self.encrypted = SimpleNamespace(
            add=Mock(return_value=29), tags=Mock(return_value=[]),
            set_tags=Mock(),
        )
        self.current = self.original
        self.route = Mock(return_value="Work")
        self.ingestion = ClipboardIngestionService(
            lambda: self.current, self.route,
        )
        self.entry = ClipboardEntry(
            "text", b"clipmint diagnostic note", "Diagnostic note",
            {"text/plain": b"clipmint diagnostic note"},
        )

    def test_routes_and_saves_into_current_store(self):
        outcome = self.ingestion.ingest(
            self.entry, "Personal", autosort_enabled=False,
        )
        self.assertEqual(outcome, IngestionResult(19, "Work"))
        self.route.assert_called_once_with(
            "text", "clipmint diagnostic note", "Personal",
            formats=self.entry.formats,
        )
        self.original.add.assert_called_once_with(
            "text", self.entry.content, "Diagnostic note", "Work",
            formats=self.entry.formats,
        )
        self.original.tags.assert_not_called()

    def test_deny_rule_never_resolves_store_or_persists(self):
        self.route.return_value = None
        result = self.ingestion.ingest(
            self.entry, "Work", autosort_enabled=True,
        )
        self.assertEqual(result, IngestionResult(None, None, True))
        self.original.add.assert_not_called()
        self.original.set_tags.assert_not_called()

    def test_runtime_encrypted_store_swap_does_not_reuse_plaintext_store(self):
        self.ingestion.ingest(self.entry, "Work", autosort_enabled=False)
        self.current = self.encrypted
        self.ingestion.ingest(
            self.entry, "Work", autosort_enabled=False,
            preview="Overridden preview",
        )
        self.original.add.assert_called_once()
        self.encrypted.add.assert_called_once_with(
            "text", self.entry.content, "Overridden preview", "Work",
            formats=self.entry.formats,
        )

    def test_tags_only_saved_entries_and_honors_tag_capacity(self):
        with patch("clipmint.clip_ingestion.classify_smart", return_value="code-snippet"):
            self.ingestion.ingest(self.entry, "Work", autosort_enabled=True)
        self.original.set_tags.assert_called_once_with(19, ["type_code_snippet"])
        self.original.set_tags.reset_mock()
        self.original.tags.return_value = [f"type_{i}" for i in range(15)]
        with patch("clipmint.clip_ingestion.classify_smart", return_value="note"):
            self.ingestion.ingest(self.entry, "Work", autosort_enabled=True)
        self.original.set_tags.assert_not_called()

    def test_window_constructs_an_explicit_service(self):
        # Keep the existing monitor mixin and signal API, but delegate storage.
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "clipmint/app.py").read_text()
        self.assertIn("ClipboardIngestionService(", source)
        self.assertIn("lambda: self.store", source)
        self.assertTrue(hasattr(ClipMintWindow, "clipboard_changed"))


if __name__ == "__main__":
    unittest.main()
