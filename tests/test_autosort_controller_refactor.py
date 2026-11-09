"""Regression tests for extracted Autosort UI/routing controller.

No clipboard samples are persisted; these are synthetic rules and text. The
existing integration tests remain responsible for actual watcher behaviour.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from clipmint.app import ClipMintWindow
from clipmint.autosort_controller import AutosortControllerMixin


class AutosortControllerExtractionTests(unittest.TestCase):
    def test_main_window_exposes_exact_original_editor_callbacks(self):
        self.assertTrue(issubclass(ClipMintWindow, AutosortControllerMixin))
        for name in (
            "build_autosort_page", "toggle_autosort", "persist_autosort",
            "refresh_autosort_list", "toggle_autosort_rule",
            "autosort_reordered", "edit_autosort_dialog",
            "add_autosort_rule", "edit_autosort_rule",
            "remove_autosort_rule", "move_autosort_rule",
            "restore_autosort_defaults", "autosort_destination",
            "test_autosort",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(ClipMintWindow, name),
                              getattr(AutosortControllerMixin, name))

    def test_disabled_autosort_does_not_change_selected_bin(self):
        context = SimpleNamespace(autosort_enabled=False)
        self.assertEqual(
            AutosortControllerMixin.autosort_destination(
                context, "text", "ordinary sample", "Work"
            ), "Work",
        )

    def test_first_matching_rule_and_private_clip_suppression(self):
        rules = [
            {"mode": "Keyword", "pattern": "invoice", "target": "Personal",
             "enabled": True},
            {"mode": "Text", "pattern": "", "target": "Work",
             "enabled": True},
        ]
        context = SimpleNamespace(
            autosort_enabled=True, autosort_rules=rules,
            store=SimpleNamespace(bins=lambda: ["Work", "Personal"]),
        )
        self.assertEqual(
            AutosortControllerMixin.autosort_destination(
                context, "text", "invoice from a shop", "Work"
            ), "Personal",
        )
        self.assertEqual(
            AutosortControllerMixin.autosort_destination(
                context, "text", "normal passage", "Personal"
            ), "Work",
        )
        self.assertIsNone(
            AutosortControllerMixin.autosort_destination(
                context, "text", "password: exampleSecret1234", "Work"
            )
        )

    def test_reordering_persists_priority_without_reformatting_rules(self):
        entries = [
            {"mode": "Keyword", "pattern": "first", "target": "Work", "enabled": True},
            {"mode": "Keyword", "pattern": "second", "target": "Personal", "enabled": True},
        ]
        state = SimpleNamespace(
            autosort_rules=entries, persist_autosort=Mock(),
            refresh_autosort_list=Mock(),
            autosort_list=SimpleNamespace(
                count=lambda: 2,
                item=lambda i: SimpleNamespace(data=lambda _role: (1, 0)[i]),
            ),
        )
        AutosortControllerMixin.autosort_reordered(state)
        self.assertEqual(state.autosort_rules[0]["pattern"], "second")
        self.assertEqual(state.autosort_rules[1]["pattern"], "first")
        state.persist_autosort.assert_called_once_with()
        state.refresh_autosort_list.assert_called_once_with()

    def test_toggle_preference_preserves_user_opt_in(self):
        state = SimpleNamespace(settings=Mock(), statusBar=Mock())
        AutosortControllerMixin.toggle_autosort(state, False)
        self.assertFalse(state.autosort_enabled)
        state.settings.setValue.assert_called_once_with("autosort/enabled", False)
        state.statusBar.return_value.showMessage.assert_called_once()


if __name__ == "__main__":
    unittest.main()
