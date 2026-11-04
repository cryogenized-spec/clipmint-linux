"""No-OS-mutation Cinnamon shortcut and optional real-Tesseract OCR tests."""
from pathlib import Path
from unittest.mock import patch
import os
import shutil
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QColor, QFont, QPainter
from PySide6.QtWidgets import QApplication

from clipmint.cinnamon_hotkey import install_shortcut, cinnamon_accelerator, ShortcutSetupError
from clipmint.ocr import extract_text


class CinnamonShortcutTests(unittest.TestCase):
    def test_accelerator_mapping_and_invalid(self):
        self.assertEqual(cinnamon_accelerator("Ctrl+Alt+V"), "<Primary><Alt>v")
        self.assertEqual(cinnamon_accelerator("Meta+Shift+F10"), "<Super><Shift>f10")
        with self.assertRaises(ShortcutSetupError):
            cinnamon_accelerator("V")
        with self.assertRaises(ShortcutSetupError):
            cinnamon_accelerator("Ctrl+Alt+Something")

    def _fake_gsettings(self, with_conflict=False):
        calls = []
        schema = ("org.cinnamon.desktop.keybindings.custom-keybinding:"
                  "/org/cinnamon/desktop/keybindings/custom-keybindings/custom0/")
        values = {
            ("org.cinnamon.desktop.keybindings", "custom-list"): "['custom0']",
            (schema, "binding"): "['<Primary><Alt>v']" if with_conflict
                                else "['<Primary><Alt>x']",
            (schema, "command"): "'other-app'",
            (schema, "name"): "'Other app'",
        }

        def run(*args):
            calls.append(args)
            if args[0] == "get":
                return values[(args[1], args[2])]
            if args[0] == "list-recursively":
                return ""  # No global desktop conflicts in this test fixture.
            if args[0] == "set":
                values[(args[1], args[2])] = args[3]
                return ""
            raise AssertionError(args)
        return run, calls, values

    def test_registration_appends_a_free_slot_without_overwrite(self):
        fake_run, calls, values = self._fake_gsettings()
        with patch("clipmint.cinnamon_hotkey._run", side_effect=fake_run):
            self.assertEqual(install_shortcut(
                "/opt/clipmint/ClipMint --toggle", "Ctrl+Alt+V"
            ), "<Primary><Alt>v")
        self.assertIn(("set", "org.cinnamon.desktop.keybindings",
                       "custom-list", "['custom0', 'custom1']"), calls)
        self.assertFalse(any(
            "custom0/" in str(x) and x[0] == "set" for x in calls
        ))
        self.assertEqual(values[("org.cinnamon.desktop.keybindings", "custom-list")],
                         "['custom0', 'custom1']")

    def test_existing_binding_is_never_modified(self):
        fake_run, calls, _values = self._fake_gsettings(with_conflict=True)
        with patch("clipmint.cinnamon_hotkey._run", side_effect=fake_run):
            with self.assertRaises(ShortcutSetupError):
                install_shortcut("clipmint --toggle", "Ctrl+Alt+V")
        self.assertFalse(any(call[0] == "set" for call in calls))

class RealOcrTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("tesseract"), "Tesseract not installed in this runner")
    def test_reads_large_clear_test_image_offline(self):
        app = QApplication.instance() or QApplication([])
        image = QImage(850, 160, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setFont(QFont("DejaVu Sans", 43, QFont.Weight.Bold))
        painter.setPen(QColor("black"))
        painter.drawText(image.rect(), 0x84, "CLIPMINT 12345")
        painter.end()
        arr = QByteArray()
        buf = QBuffer(arr)
        self.assertTrue(buf.open(QIODevice.OpenModeFlag.WriteOnly))
        self.assertTrue(image.save(buf, "PNG"))
        buf.close()
        result = extract_text(bytes(arr)).upper()
        self.assertIn("CLIPMINT", result)
        self.assertIn("12345", result)


if __name__ == "__main__":
    unittest.main()
