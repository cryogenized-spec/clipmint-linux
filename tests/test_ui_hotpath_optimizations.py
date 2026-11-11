"""Hot-path performance contracts without timing-sensitive thresholds.

Background history refresh reuses the same stored total count. The painted
footer resolves the registered font once per widget, never once per repaint.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtWidgets import QApplication
from clipmint.crimson_widgets import CrimsonFooterButton
from clipmint.history_controller import HistoryControllerMixin


class UiHotPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_history_total_count_only_queried_once_per_refresh(self):
        store = Mock()
        store.all_tags.return_value = []
        store.search.return_value = []
        store.count.return_value = 17
        store.index_status.return_value = "Synthetic index"

        history = Mock()
        history.currentItem.return_value = None
        tags = Mock()
        tags.currentData.return_value = ""
        tags.findData.return_value = -1
        sort = Mock()
        sort.currentData.return_value = "Latest first"
        state = SimpleNamespace(
            _history_search_timer=Mock(),
            history=history,
            selected_id=lambda: None,
            view_bin=lambda: "Work",
            tabs=Mock(),
            sort_combo=sort,
            tag_filter=tags,
            search=Mock(),
            store=store,
            favorites_filter=Mock(),
            settings=Mock(),
            count_label=Mock(),
            _refresh_queue_button=Mock(),
            footer_status=Mock(),
            history_secure=False,
            history_security_error="",
            monitoring=True,
            clear_preview=Mock(),
        )
        state.search.text.return_value = ""
        state.favorites_filter.isChecked.return_value = False
        state.settings.value.return_value = False
        with patch("clipmint.history_controller.selected_category", return_value="All"):
            HistoryControllerMixin.refresh(state)

        store.count.assert_called_once_with("Work")
        state.count_label.setText.assert_called_once_with("00 / 17")
        state.footer_status.setText.assert_called_once_with(
            "● MONITORING ACTIVE   |   HISTORY 17"
        )
        state.footer_status.setToolTip.assert_called_once_with(
            "17 clips in Work"
        )

    def test_footer_font_lookup_occurs_only_during_first_paint(self):
        button = CrimsonFooterButton("● Capture", True)
        try:
            with patch(
                "clipmint.crimson_widgets._footer_title_font_family",
                return_value="Georgia",
            ) as font:
                for _ in range(3):
                    image = button.grab()
                    self.assertFalse(image.isNull())
                font.assert_called_once_with()
                self.assertEqual(button._title_font_family, "Georgia")
        finally:
            button.deleteLater()
            self.app.processEvents()

    def test_footer_fonts_resolve_independently_per_widget(self):
        first = CrimsonFooterButton("● Capture", True)
        second = CrimsonFooterButton("▣ Screenshot", False)
        try:
            with patch(
                "clipmint.crimson_widgets._footer_title_font_family",
                return_value="Cormorant Garamond",
            ) as font:
                first.grab()
                second.grab()
                first.grab()
                second.grab()
                self.assertEqual(font.call_count, 2)
                self.assertEqual(first._title_font_family, "Cormorant Garamond")
                self.assertEqual(second._title_font_family, "Cormorant Garamond")
        finally:
            first.deleteLater()
            second.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
