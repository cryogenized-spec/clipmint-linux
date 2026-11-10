"""Preserve exported painted widget identities and Gothic Archive visuals."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtWidgets import QApplication

from clipmint import crimson_ui, crimson_widgets


class CrimsonWidgetExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_existing_crimson_ui_exports_preserve_identity(self):
        for name in (
            "GothicSearchCapsule", "GothicDivider",
            "CrimsonFooterButton", "CrimsonFooterArrow",
            "CrimsonClipDelegate", "label_type",
            "ROSE", "LIME", "PORCELAIN", "MUTED",
        ):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(crimson_ui, name), getattr(crimson_widgets, name)
                )

    def test_label_classification_preserved(self):
        cases = [
            ("image", "sample", "IMG"),
            ("files", "file:///home/test", "FILE"),
            ("text", "https://example.test/", "URL"),
            ("text", "#AABBCC", "HEX"),
            ("text", "sudo apt update", "CODE"),
            ("text", "ordinary note", "TXT"),
        ]
        for kind, preview, expected in cases:
            with self.subTest(kind=kind, preview=preview):
                self.assertEqual(
                    crimson_ui.label_type(kind, preview)[0], expected
                )

    def test_painted_widgets_render_offscreen_without_changes_to_apis(self):
        widgets = [
            crimson_ui.GothicSearchCapsule(),
            crimson_ui.GothicDivider(),
            crimson_ui.CrimsonFooterButton("● Capture", True),
            crimson_ui.CrimsonFooterButton("▣ Screenshot", False),
            crimson_ui.CrimsonFooterArrow(True),
            crimson_ui.CrimsonFooterArrow(False),
        ]
        try:
            for widget in widgets:
                widget.resize(160, 64)
                image = widget.grab()
                self.assertFalse(image.isNull(), type(widget).__name__)
                self.assertEqual(image.width(), 160)
        finally:
            for widget in widgets:
                widget.deleteLater()
            self.app.processEvents()

    def test_main_qss_and_layout_builders_remain_in_crimson_ui(self):
        self.assertIn("QListWidget#clipHistory", crimson_ui.CRIMSON_QSS)
        self.assertIn("QWidget#archivePage", crimson_ui.CRIMSON_QSS)
        self.assertTrue(callable(crimson_ui.build_crimson_ui))
        self.assertTrue(callable(crimson_ui.build_archive_page))


if __name__ == "__main__":
    unittest.main()
