"""Contract tests for opt-in tagged GitHub Releases and portable checksums."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowTests(unittest.TestCase):
    def test_release_requires_version_tag_and_successful_build(self):
        workflow = (ROOT / ".github/workflows/build-linux.yml").read_text()
        self.assertIn("push:\n    tags:", workflow)
        self.assertIn("'v[0-9]*.[0-9]*.[0-9]*'", workflow)
        self.assertIn("if: github.event_name == 'push'", workflow)
        self.assertIn("needs: build", workflow)
        self.assertIn("sha256sum --check SHA256SUMS", workflow)
        self.assertIn("GH_REPO: ${{ github.repository }}", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("dist-packages/SHA256SUMS", workflow)
        self.assertIn("--verify-tag", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn('[[ "$GITHUB_REF_NAME" =~ ^v', workflow)

    def test_checksums_reference_downloaded_filename_not_build_path(self):
        build = (ROOT / "packaging/build-deb.sh").read_text()
        self.assertIn('(cd dist-packages && sha256sum', build)
        self.assertIn('> SHA256SUMS)', build)


if __name__ == "__main__":
    unittest.main()
