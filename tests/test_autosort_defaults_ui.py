"""First-run smart Autosort UX and backwards-compatible preference tests."""
from __future__ import annotations

import os
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtWidgets import QApplication

from clipmint.app import ClipMintWindow
from clipmint.smart_types import DEFAULT_BINS


class SmartAutosortUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_active_presets_first_launch_and_existing_choices_preserved(self):
        with TemporaryDirectory() as root:
            prior_data = os.environ.get("XDG_DATA_HOME")
            prior_config = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_DATA_HOME"] = root
            os.environ["XDG_CONFIG_HOME"] = root
            first = second = third = None
            try:
                first = ClipMintWindow()
                self.assertTrue(first.autosort_enabled)
                self.assertTrue(first.autosort_switch.isChecked())
                self.assertEqual(len(first.autosort_rules), 30)
                self.assertEqual(first.autosort_list.count(), 30)
                self.assertTrue(set(DEFAULT_BINS).issubset(first.store.bins()))
                self.assertEqual(first.autosort_destination(
                    "text", "https://example.org/?utm_campaign=demo", "Work"), "Web")
                self.assertIsNone(first.autosort_destination(
                    "text", "123456", "Work"))
                self.assertEqual(first.autosort_destination(
                    "text", "def fx(x):\n    return x * 2", "Work"),
                    "Development")

                # Preserve explicit user choices, including disabled state.
                first.toggle_autosort(False)
                first.autosort_rules = [
                    {"mode": "Keyword", "pattern": "quotation",
                     "target": "Personal", "enabled": True}
                ]
                first.persist_autosort()
                first.settings.sync()
                first.poller.stop()
                first._vault_lock_timer.stop()
                first.store.close()
                first.hide()
                first = None

                second = ClipMintWindow()
                self.assertFalse(second.autosort_enabled)
                self.assertEqual(len(second.autosort_rules), 1)
                self.assertEqual(second.autosort_rules[0]["pattern"], "quotation")
                self.assertEqual(
                    second.autosort_destination(
                        "text", "https://example.org", "Work"), "Work"
                )
                self.assertEqual(second.autosort_destination(
                    "text", "Text with a CLIENT_SECRET=fakeValue123", "Work"),
                    "Work")  # From MIME and storage guards, not Autosort toggle.

                # Restore 30 presets only when explicitly requested.
                second.autosort_rules = []
                second.persist_autosort()
                second.settings.sync()
                second.poller.stop()
                second._vault_lock_timer.stop()
                second.store.close()
                second.hide()
                second = None
                third = ClipMintWindow()
                self.assertEqual(third.autosort_rules, [])
            finally:
                for window in (first, second, third):
                    if window:
                        window.poller.stop()
                        window._vault_lock_timer.stop()
                        window.store.close()
                        window.hide()
                if prior_data is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = prior_data
                if prior_config is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = prior_config


if __name__ == "__main__":
    unittest.main()
