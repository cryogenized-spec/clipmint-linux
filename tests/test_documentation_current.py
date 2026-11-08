"""Prevent outdated installation and update instructions from returning."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CurrentDocumentationTests(unittest.TestCase):
    def test_readme_describes_current_preview_not_old_draft_prs(self):
        readme = (ROOT / "README.md").read_text()
        self.assertTrue(readme.startswith("# ClipMint —"))
        self.assertIn("Linux Mint 22", readme)
        self.assertNotIn("## v0.4 development preview", readme)
        self.assertNotIn("draft PR #", readme)
        for filename in ("CHANGELOG.md", "ROADMAP.md", "SECURITY.md"):
            self.assertIn(f"]({filename})", readme)
            self.assertTrue((ROOT / filename).is_file())

    def test_current_docs_do_not_conflate_checksum_and_authentication(self):
        readme = (ROOT / "README.md").read_text()
        security = (ROOT / "SECURITY.md").read_text()
        self.assertIn("not independent proof of publisher identity", readme)
        self.assertIn("NOT an independently authenticated signature", security)
        self.assertIn("20 MiB", readme)
        self.assertIn("OFF by default", readme)
        self.assertIn("plaintext by default", readme)
        self.assertIn("original matching", readme)

    def test_roadmap_does_not_claim_independent_signatures_shipped(self):
        history = (ROOT / "CHANGELOG.md").read_text()
        roadmap = (ROOT / "ROADMAP.md").read_text()
        self.assertIn("Unreleased", history)
        self.assertIn("not yet complete", history)
        self.assertIn("Independently authenticate releases", roadmap)
        self.assertIn("owner-controlled", roadmap)


if __name__ == "__main__":
    unittest.main()
