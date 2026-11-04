"""Explicit, non-destructive Cinnamon global shortcut installer.

Uses Cinnamon's existing custom-keybinding mechanism. Nothing is changed
without the user clicking "Register". Existing bindings are never overwritten.
"""
from __future__ import annotations
import ast
import re
import shutil
import subprocess
import shlex

PARENT = "org.cinnamon.desktop.keybindings"
CHILD = "org.cinnamon.desktop.keybindings.custom-keybinding"
BASE = "/org/cinnamon/desktop/keybindings/custom-keybindings/"


class ShortcutSetupError(RuntimeError):
    pass


def cinnamon_accelerator(sequence: str) -> str:
    parts = [x.strip() for x in sequence.split("+")]
    if len(parts) < 2:
        raise ShortcutSetupError("Use at least one modifier and a letter")
    key = parts[-1]
    if not re.fullmatch(r"[A-Za-z0-9]|F(?:[1-9]|1[0-2])", key):
        raise ShortcutSetupError("Choose a letter, digit or F1–F12 shortcut")
    modifiers = {"Ctrl":"<Primary>", "Control":"<Primary>",
                 "Alt":"<Alt>", "Shift":"<Shift>", "Meta":"<Super>",
                 "Super":"<Super>"}
    try:
        prefix = "".join(modifiers[p] for p in parts[:-1])
    except KeyError as exc:
        raise ShortcutSetupError(f"Unsupported shortcut modifier: {exc}") from exc
    if not prefix:
        raise ShortcutSetupError("Global shortcuts must use a modifier")
    return prefix + key.lower()


def _run(*args):
    if not shutil.which("gsettings"):
        raise ShortcutSetupError("GSettings is unavailable; configure the shortcut in Cinnamon settings")
    try:
        result = subprocess.run(["gsettings", *args], text=True,
                                capture_output=True, timeout=3, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ShortcutSetupError("Could not communicate with Cinnamon settings") from exc
    if result.returncode:
        raise ShortcutSetupError("Cinnamon rejected this shortcut setting")
    return result.stdout.strip()


def _list(value: str) -> list[str]:
    if value.startswith("@as "):
        value = value[4:]
    try:
        result = ast.literal_eval(value)
    except (ValueError, SyntaxError) as exc:
        raise ShortcutSetupError("Cannot parse Cinnamon shortcut settings") from exc
    if not isinstance(result, list) or not all(isinstance(x, str) for x in result):
        raise ShortcutSetupError("Unexpected Cinnamon shortcut settings")
    return result


MEDIA_KEYS = "org.cinnamon.desktop.keybindings.media-keys"
SCREENSHOT_ACTIONS = (
    "screenshot", "window-screenshot", "area-screenshot",
    "screenshot-clip", "window-screenshot-clip", "area-screenshot-clip",
)


def _canonical(accelerator: str) -> tuple[tuple[str, ...], str]:
    """Compare common GSettings modifier spellings independently of order."""
    modifier_names = re.findall(r"<([^>]+)>", accelerator)
    aliases = {"control": "primary", "ctrl": "primary", "super": "super"}
    modifiers = tuple(sorted(aliases.get(name.lower(), name.lower())
                             for name in modifier_names))
    key = re.sub(r"<[^>]+>", "", accelerator).lower()
    return modifiers, key


def _check_cinnamon_screenshot_conflicts(accelerator: str) -> None:
    requested = _canonical(accelerator)
    # Do not silently replace Mint's built-in screenshot shortcuts. The user
    # can reassign them explicitly in the system keyboard settings.
    for action in SCREENSHOT_ACTIONS:
        try:
            bindings = _list(_run("get", MEDIA_KEYS, action))
        except ShortcutSetupError:
            continue  # Older Cinnamon version may not have every key.
        if any(_canonical(bound) == requested for bound in bindings if bound):
            raise ShortcutSetupError(
                "Cinnamon's built-in screenshot action already owns this key. "
                "Open System Settings → Keyboard → Shortcuts → Screenshots "
                "and remove or change that binding before registering ClipMint."
            )


def install_shortcut(
    command: str,
    sequence: str = "Ctrl+Alt+V",
    *,
    name: str = "ClipMint quick search",
) -> str:
    accelerator = cinnamon_accelerator(sequence)
    current = _list(_run("get", PARENT, "custom-list"))
    for ident in current:
        schema = f"{CHILD}:{BASE}{ident}/"
        existing = _list(_run("get", schema, "binding"))
        if any(_canonical(bound) == _canonical(accelerator) for bound in existing):
            existing_command = _run("get", schema, "command").strip("'")
            if existing_command == command:
                return accelerator  # Idempotent registration of our own shortcut.
            raise ShortcutSetupError(
                "That key combination is already assigned to a Cinnamon custom "
                "shortcut. Change it under System Settings → Keyboard → "
                "Shortcuts → Custom Shortcuts first."
            )
    _check_cinnamon_screenshot_conflicts(accelerator)
    # Never overwrite existing custom shortcuts. New registration is opt-in.
    slot = next(f"custom{i}" for i in range(1000) if f"custom{i}" not in current)
    schema = f"{CHILD}:{BASE}{slot}/"
    for key, value in (
        ("name", name),
        ("command", command),
        ("binding", str([accelerator])),
    ):
        _run("set", schema, key, value)
    updated = _list(_run("get", PARENT, "custom-list"))
    if slot in updated:
        raise ShortcutSetupError("Cinnamon shortcut list changed concurrently")
    _run("set", PARENT, "custom-list", str(updated + [slot]))
    return accelerator
