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

    def test_registration_appends_a_free_slot_without_overwrite(self):
        calls = []
        def fake_run(*args):
            calls.append(args)
            if args == ("get", "org.cinnamon.desktop.keybindings", "custom-list"):
                return "['custom0']"
            if args[0] == "get" and args[-1] == "binding":
                return "['<Primary><Alt>x']"
            return ""
        with patch("clipmint.cinnamon_hotkey._run", side_effect=fake_run):
            self.assertEqual(install_shortcut(
                "/opt/clipmint/ClipMint --toggle", "Ctrl+Alt+V"
            ), "<Primary><Alt>v")
        self.assertIn(("set", "org.cinnamon.desktop.keybindings",
                       "custom-list", "['custom0', 'custom1']"), calls)
        self.assertFalse(any(
            "custom0/" in str(x) and x[0] == "set" for x in calls
        ))

    def test_existing_binding_is_never_modified(self):
        with patch("clipmint.cinnamon_hotkey._run",
                   side_effect=["['custom0']", "['<Primary><Alt>v']"]) as run:
            with self.assertRaises(ShortcutSetupError):
                install_shortcut("clipmint --toggle", "Ctrl+Alt+V")
        self.assertEqual(run.call_count, 2)


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
