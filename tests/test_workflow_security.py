"""CI supply-chain guardrails: only release publisher may write GitHub content."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
EXPECTED = {
    "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
    "actions/download-artifact": "d3f86a106a0bac45b974a628896c90dbdf5c8093",
}


class WorkflowSecurityTests(unittest.TestCase):
    def test_actions_use_exact_reviewed_commit_hashes(self):
        for workflow in WORKFLOWS.glob("*.yml"):
            content = workflow.read_text(encoding="utf-8")
            actions = re.findall(r"^\s*- uses: (actions/[\w-]+)@([^\s#]+)",
                                 content, flags=re.MULTILINE)
            for action, revision in actions:
                with self.subTest(workflow=workflow.name, action=action):
                    self.assertIn(action, EXPECTED)
                    self.assertEqual(revision, EXPECTED[action])

    def test_nonpublishing_jobs_are_read_only(self):
        for filename in (
            "tests.yml", "crimson-native-review.yml",
            "review-screenshot-gallery.yml", "ui-preview.yml"
        ):
            with self.subTest(filename=filename):
                workflow = (WORKFLOWS / filename).read_text()
                self.assertIn("permissions:\n  contents: read", workflow)
                self.assertNotIn("contents: write", workflow)

    def test_publisher_has_read_only_workflow_default(self):
        workflow = (WORKFLOWS / "build-linux.yml").read_text()
        self.assertIn("permissions:\n  contents: read", workflow)
        # Only the two publishing jobs may request write permission.
        self.assertEqual(workflow.count("contents: write"), 2)

    def test_ui_preview_does_not_write_git_history_or_b64_files(self):
        workflow = (WORKFLOWS / "ui-preview.yml").read_text()
        self.assertNotIn("git push", workflow)
        self.assertNotIn("git commit", workflow)
        self.assertNotIn(".b64", workflow)
        self.assertIn("actions/upload-artifact@", workflow)


if __name__ == "__main__":
    unittest.main()
