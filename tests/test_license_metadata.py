"""Ensure ClipMint code and generated installer declare AGPL consistently."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LicenseMetadataTests(unittest.TestCase):
    def test_canonical_agpl_is_complete_and_selected(self):
        data = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(data.startswith("GNU AFFERO GENERAL PUBLIC LICENSE"))
        self.assertIn("Version 3, 19 November 2007", data)
        self.assertIn("13. Remote Network Interaction", data)
        self.assertIn("END OF TERMS AND CONDITIONS", data)
        self.assertGreater(len(data), 33000)

    def test_readme_and_notice_distinguish_license_scopes(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        notice = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
        mit = (ROOT / "LICENSES/MIT-legacy.txt").read_text(encoding="utf-8")
        self.assertIn("AGPL-3.0-only", readme)
        self.assertNotIn("Original ClipMint code: MIT.", readme)
        self.assertIn("AGPL-3.0-only", notice)
        self.assertIn("SIL Open Font License 1.1", notice)
        self.assertIn("not", notice.lower())
        self.assertIn("MIT License", mit)
        self.assertIn("Copyright (c) 2026 ClipMint contributors", mit)

    def test_package_ships_license_source_and_notices(self):
        build = (ROOT / "packaging/build-deb.sh").read_text(encoding="utf-8")
        verify = (ROOT / "packaging/verify-field-package.sh").read_text(encoding="utf-8")
        for name in ("LICENSE-ClipMint", "MIT-legacy.txt",
                     "THIRD-PARTY-NOTICES.md", "SOURCE-CODE.txt"):
            self.assertIn(name, build)
            self.assertIn(name, verify)
        self.assertIn("git rev-parse HEAD", build)
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", verify)


if __name__ == "__main__":
    unittest.main()
