"""Cinnamon keyboard shortcut ownership, takeover, rollback and restore tests.

All gsettings calls are mocked: no real desktop shortcuts are changed in CI.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from clipmint import cinnamon_hotkey as h
from clipmint.single_instance import VALID_COMMANDS


class ShortcutRegistrationTests(unittest.TestCase):
    def fake_gsettings(
        self, custom: list[str] | None = None,
        bindings: dict[str, list[str]] | None = None,
        other: dict[tuple[str, str], list[str]] | None = None,
    ):
        custom = list(custom or [])
        bindings = bindings or {}
        other = other or {}
        values = {(h.PARENT, "custom-list"): repr(custom)}
        for action in h.SCREENSHOT_ACTIONS:
            values[(h.MEDIA_KEYS, action)] = repr(bindings.get(action, [""]))
        for (schema, key), value in other.items():
            values[(schema, key)] = repr(value)
        for ident in custom:
            schema = f"{h.CHILD}:{h.BASE}{ident}/"
            values[(schema, "binding")] = "['<Primary><Shift>s']"
            values[(schema, "command")] = "'/opt/clipmint/ClipMint --screenshot-area'"
            values[(schema, "name")] = "'ClipMint screenshot area'"
        writes = []
        state = {"fail_once": None}

        def runner(verb, *args):
            if verb == "get":
                return values[(args[0], args[1])]
            if verb == "list-recursively":
                schema = args[0]
                if schema not in (h.MEDIA_KEYS, *h.OTHER_SCHEMAS):
                    raise h.ShortcutSetupError("Unknown Cinnamon schema")
                return "\n".join(
                    f"{schema} {key} {value}"
                    for (key_schema, key), value in values.items()
                    if key_schema == schema
                )
            if verb == "set":
                schema, key, value = args
                if state["fail_once"] == (schema, key):
                    state["fail_once"] = None
                    raise h.ShortcutSetupError("Simulated GSettings write failure")
                values[(schema, key)] = value
                writes.append((schema, key, value))
                return ""
            raise AssertionError(verb)

        return runner, writes, values, state

    def test_registration_owns_global_screenshot_key(self):
        run, writes, vals, _state = self.fake_gsettings()
        with patch.object(h, "_run", side_effect=run):
            result = h.install_shortcut(
                "/opt/clipmint/ClipMint --screenshot-area",
                "Ctrl+Shift+S", name="ClipMint screenshot area",
            )
            self.assertEqual(len(h.shortcut_conflicts("Ctrl+Shift+S")), 1)
        self.assertEqual(result, "<Primary><Shift>s")
        schema = f"{h.CHILD}:{h.BASE}custom0/"
        self.assertEqual(vals[(schema, "binding")], "['<Primary><Shift>s']")
        self.assertEqual(vals[(schema, "name")], "ClipMint screenshot area")
        self.assertEqual(vals[(schema, "command")],
                         "/opt/clipmint/ClipMint --screenshot-area")
        self.assertEqual(vals[(h.PARENT, "custom-list")], "['custom0']")
        self.assertEqual(len(writes), 4)

    def test_builtin_collision_requires_explicit_consent(self):
        run, writes, _vals, _state = self.fake_gsettings(
            bindings={"area-screenshot": ["<Shift><Control>s"]}
        )
        with patch.object(h, "_run", side_effect=run):
            with self.assertRaisesRegex(h.ShortcutSetupError, "Explicit permission"):
                h.install_shortcut("clipmint --screenshot-area", "Ctrl+Shift+S")
        self.assertEqual(writes, [])

    def test_explicit_takeover_preserves_other_keys_and_restores_backup(self):
        run, writes, vals, _state = self.fake_gsettings(
            bindings={"area-screenshot": ["<Shift><Control>s", "<Shift>Print"]}
        )
        command = "/opt/clipmint/ClipMint --screenshot-area"
        with TemporaryDirectory() as root:
            backup = Path(root) / "cinnamon-bindings.json"
            with patch.object(h, "_run", side_effect=run), \
                 patch.object(h, "_backup_path", return_value=backup):
                result = h.install_shortcut(
                    command, "Ctrl+Shift+S",
                    name="ClipMint screenshot area",
                    take_over_screenshot=True,
                )
                self.assertEqual(result, "<Primary><Shift>s")
                self.assertEqual(
                    h._list(vals[(h.MEDIA_KEYS, "area-screenshot")]),
                    ["<Shift>Print"],
                )
                self.assertEqual(len(h.shortcut_conflicts("Ctrl+Shift+S")), 1)
                self.assertTrue(backup.exists())
                self.assertTrue(h.restore_screenshot_takeover(command, "Ctrl+Shift+S"))
                self.assertFalse(h.restore_screenshot_takeover(command, "Ctrl+Shift+S"))
            self.assertEqual(
                h._list(vals[(h.MEDIA_KEYS, "area-screenshot")]),
                ["<Shift><Control>s", "<Shift>Print"],
            )
            self.assertEqual(vals[(h.PARENT, "custom-list")], "[]")

    def test_cannot_overwrite_window_manager_or_foreign_custom_shortcut(self):
        run, writes, _vals, _state = self.fake_gsettings(
            other={(h.OTHER_SCHEMAS[0], "toggle-maximized"):
                   ["<Primary><Shift>s"]}
        )
        with patch.object(h, "_run", side_effect=run):
            with self.assertRaisesRegex(h.ShortcutSetupError, "window-manager"):
                h.install_shortcut("clipmint --screenshot-area", "Ctrl+Shift+S",
                                   take_over_screenshot=True)
        self.assertEqual(writes, [])

        run, writes, _vals, _state = self.fake_gsettings(custom=["custom0"])
        with patch.object(h, "_run", side_effect=run):
            self.assertEqual(
                h.install_shortcut("/opt/clipmint/ClipMint --screenshot-area",
                                   "Ctrl+Shift+S", name="ClipMint screenshot area"),
                "<Primary><Shift>s",
            )
            with self.assertRaisesRegex(h.ShortcutSetupError, "another Cinnamon"):
                h.install_shortcut("some-other-tool", "Ctrl+Shift+S")
        self.assertEqual(writes, [])

    def test_failed_registration_rolls_back_system_shortcut(self):
        run, writes, vals, state = self.fake_gsettings(
            bindings={"area-screenshot": ["<Shift><Control>s"]}
        )
        state["fail_once"] = (h.PARENT, "custom-list")
        with TemporaryDirectory() as root:
            with patch.object(h, "_run", side_effect=run), \
                 patch.object(h, "_backup_path",
                              return_value=Path(root) / "shortcut-backup.json"):
                with self.assertRaisesRegex(h.ShortcutSetupError, "Simulated"):
                    h.install_shortcut(
                        "clipmint --screenshot-area", "Ctrl+Shift+S",
                        take_over_screenshot=True,
                    )
        self.assertEqual(vals[(h.MEDIA_KEYS, "area-screenshot")],
                         "['<Shift><Control>s']")
        self.assertEqual(vals[(h.PARENT, "custom-list")], "[]")

    def test_system_recording_key_registered_separately(self):
        run, writes, vals, _state = self.fake_gsettings()
        with patch.object(h, "_run", side_effect=run):
            h.install_shortcut("/opt/clipmint/ClipMint --record-area",
                               "Ctrl+Shift+R", name="ClipMint record area")
        schema = f"{h.CHILD}:{h.BASE}custom0/"
        self.assertEqual(vals[(schema, "command")],
                         "/opt/clipmint/ClipMint --record-area")
        self.assertEqual(vals[(schema, "binding")], "['<Primary><Shift>r']")

    def test_both_capture_commands_supported_by_ipc(self):
        self.assertIn("screenshot-area", VALID_COMMANDS)
        self.assertIn("record-area", VALID_COMMANDS)


if __name__ == "__main__":
    unittest.main()
