"""Architecture contract: app.py coordinates instead of owning page logic."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import unittest

from clipmint.app import ClipMintWindow, THEME
from clipmint.window_theme import THEME as WINDOW_THEME
from clipmint.clipboard_page import build_clipboard_page, build_info_page
from clipmint.vault_page import build_vault_page
from clipmint.window_layout import update_manga_visibility
from clipmint.window_actions import copy_clip, view_bin


class WindowCoordinatorTests(unittest.TestCase):
    def test_legacy_style_export_and_view_builders_remain_importable(self):
        self.assertIs(THEME, WINDOW_THEME)
        for func in (
            build_clipboard_page, build_info_page, build_vault_page,
            update_manga_visibility, copy_clip, view_bin,
        ):
            self.assertTrue(callable(func))

    def test_main_window_delegates_page_building_and_responsive_layout(self):
        state = object()
        for method, path, args in (
            ("build_clipboard_page", "clipmint.app.compose_clipboard_page", ()),
            ("build_vault_page", "clipmint.app.compose_vault_page", ()),
            ("build_info_page", "clipmint.app.compose_info_page", ("Title", "Body")),
            ("_update_manga_visibility", "clipmint.app.apply_manga_layout", ()),
        ):
            with self.subTest(method=method), patch(path) as delegate:
                getattr(ClipMintWindow, method)(state, *args)
                delegate.assert_called_once_with(state, *args)

    def test_window_actions_keep_public_callback_names(self):
        state = object()
        for name, args in (
            ("view_bin", ()),
            ("active_bin", ()),
            ("new_bin", ()),
            ("open_section", (2,)),
            ("_schedule_history_search", ()),
            ("copy_selected", ()),
            ("copy_clip", ("item",)),
        ):
            with self.subTest(name=name), patch(
                f"clipmint.app.window_actions.{name}"
            ) as delegate:
                getattr(ClipMintWindow, name)(state, *args)
                delegate.assert_called_once_with(state, *args)

    def test_app_is_primarily_wiring_and_has_no_widget_page_construction(self):
        source = (
            Path(__file__).resolve().parents[1] / "clipmint" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertLessEqual(len(source.splitlines()), 350)
        self.assertNotIn("QVBoxLayout(", source)
        self.assertNotIn("QInputDialog.getText(", source)
        self.assertIn("app.setQuitOnLastWindowClosed(False)", source)
        self.assertIn("self._hidden_text_probe.observe(", source)


if __name__ == "__main__":
    unittest.main()
