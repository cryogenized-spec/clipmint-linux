"""Kohaku archive layout, full-body asset override, and preserved working pages."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication
from clipmint.app import ClipMintWindow
from clipmint.manga import CrimsonMaidPortrait


class KohakuGothicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_fullbody_art_preferred_and_not_stretched(self):
        with TemporaryDirectory() as root:
            old = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            try:
                folder = Path(root) / "clipmint"
                folder.mkdir()
                image = QImage(200, 300, QImage.Format.Format_ARGB32)
                image.fill(QColor("#C12348"))
                full_path = folder / "kohaku_full.webp"
                self.assertTrue(image.save(str(full_path), "WEBP"))
                portrait = CrimsonMaidPortrait()
                self.assertEqual(portrait.asset_path, full_path)
                self.assertEqual(portrait.portrait.width(), 200)
                self.assertEqual(portrait.portrait.height(), 300)
                self.assertEqual(portrait.accessibleName()[:7], "Crimson")
            finally:
                if old is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = old

    def test_gothic_frame_and_descriptive_navigation(self):
        with TemporaryDirectory() as root:
            old = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = root
            window = None
            try:
                window = ClipMintWindow()
                window.resize(1500, 920)
                window.show()
                self.app.processEvents()
                self.assertEqual(window.manga_dock.objectName(), "maidAlcove")
                self.assertIn("Kohaku", window.maid_caption.text())
                self.assertIn("琥珀", window.maid_caption.text())
                self.assertIn("掌底", window.kohaku_japanese.text())
                self.assertGreater(window.dock_panel.width(), 120)
                for label, control in window.nav_buttons.items():
                    self.assertTrue(control.property("dockDisplay"))
                    self.assertIn(control.property("dockDisplay"), control.text())
                    self.assertTrue(control.toolTip())
                self.assertTrue(window.autosort_switch is not None)
                self.assertTrue(window.vault_status is not None)
                self.assertTrue(window.shortcut_editors)
                self.assertTrue(window.screenshot_button.isEnabled())
                self.assertTrue(window.record_button.isEnabled())
                # Small layouts retain titles instead of icons-only navigation.
                window.resize(900, 670)
                self.app.processEvents()
                self.assertTrue(window.manga_dock.isHidden())
                for button in window.nav_buttons.values():
                    self.assertGreater(len(button.text()), 2)
            finally:
                if window is not None:
                    window.poller.stop()
                    window.store.close()
                    window.hide()
                if old is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = old


if __name__ == "__main__":
    unittest.main()
