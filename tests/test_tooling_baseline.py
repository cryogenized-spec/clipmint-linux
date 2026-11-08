"""Guard the first incremental static-analysis checks from accidental removal."""
from __future__ import annotations

from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ToolingBaselineTests(unittest.TestCase):
    def test_ruff_correctness_rules_and_incremental_mypy_are_declared(self):
        configuration = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual(configuration["tool"]["ruff"]["target-version"], "py312")
        rules = configuration["tool"]["ruff"]["lint"]["select"]
        for rule in ("E4", "E7", "E9", "F63", "F7", "F82"):
            self.assertIn(rule, rules)
        self.assertEqual(configuration["tool"]["mypy"]["python_version"], "3.12")

    def test_github_ci_runs_pinned_tools_without_laptop_downloads(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text()
        self.assertIn("ruff==0.14.2", workflow)
        self.assertIn("mypy==1.18.2", workflow)
        self.assertIn("ruff check clipmint tests packaging launcher.py", workflow)
        self.assertIn("packaging/generate-preview-bootstrap.py", workflow)
        self.assertIn("clipmint/recording_recovery.py", workflow)


if __name__ == "__main__":
    unittest.main()
