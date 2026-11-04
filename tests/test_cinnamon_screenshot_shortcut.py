"""Cinnamon global screenshot shortcut registration (mocked; no real settings changed)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from clipmint import cinnamon_hotkey as h
from clipmint.single_instance import VALID_COMMANDS


class ShortcutRegistrationTests(unittest.TestCase):
    def fake_gsettings(self, custom: list[str] | None = None,
                       bindings: dict[str, list[str]] | None = None):
        custom = list(custom or [])
        bindings = bindings or {}
        values = {
            (h.PARENT, "custom-list"): repr(custom),
        }
        for action in h.SCREENSHOT_ACTIONS:
            values[(h.MEDIA_KEYS, action)] = repr(bindings.get(action, []))
        for ident in custom:
            schema = f"{h.CHILD}:{h.BASE}{ident}/"
            values[(schema, "binding")] = "['<Primary><Shift>s']"
            values[(schema, "command")] = "'/opt/clipmint/ClipMint --screenshot-area'"
        writes = []

        def runner(verb, *args):
            if verb == "get":
                return values[(args[0], args[1])]
            if verb == "set":
                schema, key, value = args
                values[(schema, key)] = value
                writes.append((schema, key, value))
                return ""
            raise AssertionError(verb)

        return runner, writes, values

    def test_normal_registration_creates_separate_global_screenshot_action(self):
        run, writes, vals = self.fake_gsettings()
        with patch.object(h, "_run", side_effect=run):
            result = h.install_shortcut(
                "/opt/clipmint/ClipMint --screenshot-area",
                "Ctrl+Shift+S", name="ClipMint screenshot area",
            )
        self.assertEqual(result, "<Primary><Shift>s")
        schema = f"{h.CHILD}:{h.BASE}custom0/"
        self.assertEqual(vals[(schema, "binding")], "['<Primary><Shift>s']")
        self.assertEqual(vals[(schema, "name")], "ClipMint screenshot area")
        self.assertEqual(vals[(schema, "command")],
                         "/opt/clipmint/ClipMint --screenshot-area")
        self.assertEqual(vals[(h.PARENT, "custom-list")], "['custom0']")
        self.assertEqual(len(writes), 4)

    def test_cinnamon_builtin_collision_does_not_mutate_any_setting(self):
        run, writes, _vals = self.fake_gsettings(
            bindings={"area-screenshot": ["<Shift><Control>s"]}
        )
        with patch.object(h, "_run", side_effect=run):
            with self.assertRaisesRegex(h.ShortcutSetupError, "built-in screenshot"):
                h.install_shortcut("clipmint --screenshot-area", "Ctrl+Shift+S")
        self.assertEqual(writes, [])

    def test_custom_collision_is_rejected_and_self_registration_idempotent(self):
        run, writes, _vals = self.fake_gsettings(custom=["custom0"])
        with patch.object(h, "_run", side_effect=run):
            self.assertEqual(
                h.install_shortcut("/opt/clipmint/ClipMint --screenshot-area",
                                   "Ctrl+Shift+S", name="ClipMint screenshot area"),
                "<Primary><Shift>s",
            )
            with self.assertRaisesRegex(h.ShortcutSetupError, "already assigned"):
                h.install_shortcut("other-tool --shot", "Ctrl+Shift+S")
        self.assertEqual(writes, [])

    def test_cli_command_available_over_single_instance_socket(self):
        self.assertIn("screenshot-area", VALID_COMMANDS)


if __name__ == "__main__":
    unittest.main()
