"""The approved ClipMint mark must be usable both from source and frozen builds."""
from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import QApplication

from clipmint.app_icon import ICON_RELATIVE, clipmint_icon, icon_path


class AppIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # QIcon uses QPixmap, which requires a live GUI application.
        # The workflow already sets QT_QPA_PLATFORM=offscreen.
        cls._app = QApplication.instance() or QApplication([])

    def test_repository_source_icon_is_shipped_and_decodable(self):
        path = icon_path()
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, "clipmint.png")
        reader = QImageReader(str(path))
        self.assertTrue(reader.canRead(), reader.errorString())
        self.assertEqual(reader.size().width(), 96)
        self.assertEqual(reader.size().height(), 96)
        self.assertFalse(clipmint_icon().isNull())

    def test_frozen_app_uses_bundled_asset_instead_of_developer_path(self):
        with patch("sys._MEIPASS", str(Path("/opt/clipmint/_internal")), create=True):
            with patch("pathlib.Path.is_file", return_value=True):
                self.assertEqual(icon_path(), Path("/opt/clipmint/_internal") / ICON_RELATIVE)

    def test_debian_packaging_uses_desktop_icon_and_qt_bundle(self):
        base = Path(__file__).resolve().parents[1]
        workflow = (base / ".github/workflows/build-linux.yml").read_text()
        script = (base / "packaging/build-deb.sh").read_text()
        desktop = (base / "packaging/clipmint.desktop").read_text()
        self.assertIn("packaging/clipmint.png:assets/icons", workflow)
        self.assertIn("hicolor/96x96/apps/clipmint.png", script)
        self.assertIn("Icon=clipmint", desktop)


if __name__ == "__main__":
    unittest.main()
