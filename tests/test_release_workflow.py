"""Contract tests for opt-in tagged GitHub Releases and portable checksums."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowTests(unittest.TestCase):
    def test_release_requires_version_tag_and_successful_build(self):
        workflow = (ROOT / ".github/workflows/build-linux.yml").read_text()
        self.assertIn("    tags:", workflow)
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

    def test_successful_main_build_publishes_immutable_preview(self):
        """No PR/token scope may publish a privileged update candidate."""
        workflow = (ROOT / ".github/workflows/build-linux.yml").read_text()
        self.assertIn("branches: [main]", workflow)
        self.assertIn("  publish-preview:", workflow)
        self.assertIn("if: github.event_name == 'push' && github.ref == 'refs/heads/main'", workflow)
        self.assertIn("needs: build", workflow)
        self.assertIn("sha256sum --check SHA256SUMS", workflow)
        self.assertIn('test "$(dpkg-deb -f', workflow)
        self.assertIn('--prerelease --target "$GITHUB_SHA"', workflow)
        self.assertIn('tag="clipmint-preview-', workflow)
        self.assertIn('if [[ "$latest" != "$GITHUB_SHA" ]]', workflow)
        self.assertIn('contents: write', workflow)
        # Rerun-failed-jobs must reuse the exact version exported by build.
        self.assertIn('package_version: ${{ steps.version.outputs.package_version }}', workflow)
        self.assertIn('CLIPMINT_VERSION: ${{ needs.build.outputs.package_version }}', workflow)
        self.assertIn('version="${CLIPMINT_VERSION:?Missing built package version}"', workflow)
        self.assertIn('tag="clipmint-preview-${GITHUB_RUN_NUMBER}-${version##*.}"', workflow)

    def test_preview_debian_versions_change_for_each_run_and_rerun(self):
        """Repeated preview1 packages caused apt to keep an old screenshot build."""
        workflow = (ROOT / ".github/workflows/build-linux.yml").read_text()
        self.assertIn("GITHUB_RUN_NUMBER", workflow)
        self.assertIn("GITHUB_RUN_ATTEMPT", workflow)
        self.assertIn(
            'version="0.6.0~preview1.${GITHUB_RUN_NUMBER}.${GITHUB_RUN_ATTEMPT}"',
            workflow,
        )
        self.assertNotIn('version="0.6.0~preview1"\n', workflow)

    def test_checksums_reference_downloaded_filename_not_build_path(self):
        build = (ROOT / "packaging/build-deb.sh").read_text()
        self.assertIn('(cd dist-packages && sha256sum', build)
        self.assertIn('> SHA256SUMS)', build)


if __name__ == "__main__":
    unittest.main()
