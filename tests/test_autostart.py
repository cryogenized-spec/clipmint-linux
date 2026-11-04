"""No real desktop settings are touched by these autostart tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest

from clipmint.autostart import (
    AutostartError, DESKTOP_ENTRY, autostart_path, is_enabled, set_enabled,
)


class AutostartTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / "config"
        self.binary = Path(self.temp.name) / "ClipMint"
        self.binary.write_bytes(b"fake executable")
        self.path = autostart_path(self.base)

    def test_default_off_and_disable_is_noop(self):
        self.assertFalse(is_enabled(self.base))
        set_enabled(False, self.base, self.binary)
        self.assertFalse(self.path.exists())

    def test_opt_in_idempotent_and_reversible(self):
        set_enabled(True, self.base, self.binary)
        self.assertTrue(is_enabled(self.base))
        self.assertEqual(self.path.read_text(), DESKTOP_ENTRY)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertIn("Exec=/opt/clipmint/ClipMint --hidden", self.path.read_text())
        set_enabled(True, self.base, self.binary)
        set_enabled(False, self.base, self.binary)
        self.assertFalse(self.path.exists())

    def test_missing_install_cannot_turn_on(self):
        self.binary.unlink()
        with self.assertRaises(AutostartError):
            set_enabled(True, self.base, self.binary)
        self.assertFalse(self.path.exists())

    def test_existing_custom_file_is_never_overwritten_or_removed(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("[Desktop Entry]\nExec=my-custom-command\n")
        old = self.path.read_bytes()
        with self.assertRaises(AutostartError):
            set_enabled(True, self.base, self.binary)
        with self.assertRaises(AutostartError):
            set_enabled(False, self.base, self.binary)
        self.assertEqual(self.path.read_bytes(), old)

    def test_symlink_is_never_followed(self):
        target = Path(self.temp.name) / "custom.desktop"
        target.write_text("custom")
        self.path.parent.mkdir(parents=True)
        self.path.symlink_to(target)
        with self.assertRaises(AutostartError):
            set_enabled(True, self.base, self.binary)
        with self.assertRaises(AutostartError):
            set_enabled(False, self.base, self.binary)
        self.assertEqual(target.read_text(), "custom")

    def test_changed_managed_entry_must_be_kept(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(DESKTOP_ENTRY + "# custom edit\n")
        self.assertFalse(is_enabled(self.base))
        with self.assertRaises(AutostartError):
            set_enabled(False, self.base, self.binary)
        self.assertTrue(self.path.exists())


if __name__ == "__main__":
    unittest.main()
