"""Developer setup must be opt-in; normal installation remains the .deb."""
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DevLauncherTests(unittest.TestCase):
    def test_default_install_script_only_directs_to_public_release(self):
        with tempfile.TemporaryDirectory() as folder:
            process = subprocess.run(
                ["bash", str(ROOT / "install.sh")],
                cwd=folder, capture_output=True, text=True, check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("github.com/cryogenized-spec/clipmint-linux/releases",
                          process.stdout)
            self.assertNotIn("private", process.stdout.lower())
            self.assertFalse((Path(folder) / ".venv").exists())

    def test_unrecognized_option_is_rejected_without_installing(self):
        process = subprocess.run(
            ["bash", str(ROOT / "install.sh"), "--unknown"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(process.returncode, 2)
        self.assertIn("--dev", process.stderr)

    def test_developer_option_is_documented_and_launcher_accepts_venv(self):
        self.assertIn('== "--dev"', (ROOT / "install.sh").read_text())
        self.assertIn("python3 -m venv .venv",
                      (ROOT / "install.sh").read_text())
        self.assertIn(".venv/bin/python", (ROOT / "run.sh").read_text())


if __name__ == "__main__":
    unittest.main()
