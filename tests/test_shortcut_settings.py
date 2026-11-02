"""Regression checks for editable, window-local Qt keyboard shortcuts."""
import os
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication
from clipmint.app import ClipMintWindow


class ShortcutSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_edit_conflict_disable_reset_and_persistence(self):
        with TemporaryDirectory() as root:
            old_data = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            QSettings.setDefaultFormat(QSettings.Format.IniFormat)
            QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, root)
            window = None
            try:
                window = ClipMintWindow()
                self.assertEqual(window.shortcut_values["search"], "Ctrl+F")
                self.assertEqual(window.shortcut_objects["search"].context().name,
                                 "WindowShortcut")
                self.assertTrue(window.change_shortcut("search", QKeySequence("Alt+F")))
                self.assertEqual(window.shortcut_values["search"], "Alt+F")
                self.assertEqual(window.shortcut_editors["search"].keySequence()
                                 .toString(QKeySequence.SequenceFormat.PortableText), "Alt+F")
                self.assertEqual(str(window.settings.value("shortcuts/search")), "Alt+F")

                # Reject duplicates without replacing the previously saved value.
                original = window.shortcut_values["copy"]
                self.assertFalse(window.change_shortcut("copy", QKeySequence("Alt+F")))
                self.assertEqual(window.shortcut_values["copy"], original)

                self.assertTrue(window.change_shortcut("monitor", QKeySequence()))
                self.assertEqual(window.shortcut_values["monitor"], "")
                self.assertFalse(window.shortcut_objects["monitor"].isEnabled())
                self.assertTrue(window.change_shortcut("monitor",
                                                      QKeySequence("Ctrl+Shift+M")))
                self.assertTrue(window.shortcut_objects["monitor"].isEnabled())

                # A second window must read the same preferences.
                window.settings.sync()
                second = ClipMintWindow()
                try:
                    self.assertEqual(second.shortcut_values["search"], "Alt+F")
                finally:
                    second.poller.stop()
                    second.store.close()
                    second.hide()
            finally:
                if window is not None:
                    window.poller.stop()
                    window.store.close()
                    window.hide()
                if old_data is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = old_data


if __name__ == "__main__":
    unittest.main()
