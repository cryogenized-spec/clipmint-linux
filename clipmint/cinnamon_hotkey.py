"""Opt-in Cinnamon global shortcut registration and conflict-safe ownership.

Window-local QShortcuts cannot outrank Cinnamon's global keyboard grabs.
Use Cinnamon's own custom-keybinding registry; never grab X11 keys behind it.
An explicit screenshot takeover can unbind *only* a conflicting built-in
screenshot action, preserving its other bindings and providing restoration.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

PARENT = "org.cinnamon.desktop.keybindings"
CHILD = "org.cinnamon.desktop.keybindings.custom-keybinding"
BASE = "/org/cinnamon/desktop/keybindings/custom-keybindings/"
MEDIA_KEYS = "org.cinnamon.desktop.keybindings.media-keys"
OTHER_SCHEMAS = (
    "org.cinnamon.desktop.keybindings.wm",
    "org.cinnamon.muffin.keybindings",
)
SCREENSHOT_ACTIONS = (
    "screenshot", "window-screenshot", "area-screenshot",
    "screenshot-clip", "window-screenshot-clip", "area-screenshot-clip",
)


class ShortcutSetupError(RuntimeError):
    pass


def cinnamon_accelerator(sequence: str) -> str:
    parts = [part.strip() for part in sequence.split("+")]
    if len(parts) < 2:
        raise ShortcutSetupError("Use a modifier and a letter or function key")
    key = parts[-1]
    if not re.fullmatch(r"[A-Za-z0-9]|F(?:[1-9]|1[0-2])", key):
        raise ShortcutSetupError("Choose a letter, digit or F1-F12 shortcut")
    modifiers = {
        "Ctrl": "<Primary>", "Control": "<Primary>",
        "Alt": "<Alt>", "Shift": "<Shift>",
        "Meta": "<Super>", "Super": "<Super>",
    }
    try:
        prefix = "".join(modifiers[part] for part in parts[:-1])
    except KeyError as exc:
        raise ShortcutSetupError(f"Unsupported shortcut modifier: {exc}") from exc
    return prefix + key.lower()


def _canonical(accelerator: str) -> tuple[tuple[str, ...], str]:
    names = re.findall(r"<([^>]+)>", accelerator)
    aliases = {"control": "primary", "ctrl": "primary", "super": "super"}
    return (
        tuple(sorted(aliases.get(name.lower(), name.lower()) for name in names)),
        re.sub(r"<[^>]+>", "", accelerator).lower(),
    )


def _run(*args: str) -> str:
    if not shutil.which("gsettings"):
        raise ShortcutSetupError("Cinnamon GSettings unavailable")
    try:
        result = subprocess.run(
            ["gsettings", *args], capture_output=True, text=True,
            check=False, timeout=4
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ShortcutSetupError("Could not read Cinnamon shortcut settings") from exc
    if result.returncode:
        raise ShortcutSetupError(
            f"Cinnamon could not {args[0]} the requested shortcut setting"
        )
    return result.stdout.strip()


def _list(value: str) -> list[str]:
    if value.startswith("@as "):
        value = value[4:]
    try:
        result = ast.literal_eval(value)
    except (ValueError, SyntaxError) as exc:
        raise ShortcutSetupError("Cannot parse Cinnamon keybinding values") from exc
    if not isinstance(result, list) or not all(isinstance(item, str) for item in result):
        raise ShortcutSetupError("Unexpected Cinnamon keybinding format")
    return result


def _custom_schema(ident: str) -> str:
    return f"{CHILD}:{BASE}{ident}/"


def _custom_conflicts(accelerator: str) -> list[dict]:
    current = _list(_run("get", PARENT, "custom-list"))
    found = []
    for ident in current:
        schema = _custom_schema(ident)
        entries = _list(_run("get", schema, "binding"))
        if any(_canonical(item) == _canonical(accelerator) for item in entries if item):
            found.append({
                "source": "custom", "key": ident,
                "command": _run("get", schema, "command").strip("'"),
                "name": _run("get", schema, "name").strip("'"),
            })
    return found


def _builtin_conflicts(accelerator: str) -> list[dict]:
    """Check Cinnamon's media/window-manager registries, not screenshot keys alone."""
    found = []
    success = False
    for schema in (MEDIA_KEYS, *OTHER_SCHEMAS):
        try:
            output = _run("list-recursively", schema)
        except ShortcutSetupError:
            # Optional window-manager schemas differ across Cinnamon releases.
            if schema == MEDIA_KEYS:
                raise
            continue
        success = True
        for line in output.splitlines():
            fields = line.split(maxsplit=2)
            if len(fields) != 3:
                continue
            _schema, key, value = fields
            if _schema != schema or not value.lstrip().startswith(("[", "@as ")):
                continue
            try:
                bindings = _list(value)
            except ShortcutSetupError:
                continue
            if any(_canonical(item) == _canonical(accelerator)
                   for item in bindings if item):
                found.append({
                    "source": "builtin", "schema": schema,
                    "key": key, "bindings": bindings,
                })
    if not success:
        raise ShortcutSetupError("Cannot inspect Cinnamon's global shortcut registry")
    return found


def shortcut_conflicts(sequence: str) -> list[dict]:
    """Read-only conflict report. Never changes desktop settings."""
    accelerator = cinnamon_accelerator(sequence)
    return _custom_conflicts(accelerator) + _builtin_conflicts(accelerator)


def _backup_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "clipmint" / "cinnamon-keybinding-backups.json"


def _load_backups() -> list[dict]:
    path = _backup_path()
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("version") != 1 or not isinstance(doc.get("takeovers"), list):
            raise ValueError("Invalid backup schema")
        return doc["takeovers"]
    except (OSError, ValueError, TypeError) as exc:
        raise ShortcutSetupError(
            "Cinnamon shortcut backup could not be read; no changes made"
        ) from exc


def _save_backups(entries: list[dict]) -> None:
    path = _backup_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    try:
        fd = os.open(temp, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            json.dump({"version": 1, "takeovers": entries}, writer, indent=2)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temp, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        raise ShortcutSetupError("Could not save Cinnamon shortcut restoration backup") from exc
    finally:
        temp.unlink(missing_ok=True)


def install_shortcut(
    command: str, sequence: str = "Ctrl+Alt+V",
    *, name: str = "ClipMint quick search",
    take_over_screenshot: bool = False,
) -> str:
    """Register globally, optionally taking over *only* built-in screenshot keys.

    The caller must obtain an explicit user confirmation before passing
    take_over_screenshot=True. Other custom/system bindings are never removed.
    """
    accelerator = cinnamon_accelerator(sequence)
    current = _list(_run("get", PARENT, "custom-list"))
    conflicts = shortcut_conflicts(sequence)
    own = [c for c in conflicts
           if c["source"] == "custom" and c["command"] == command]
    other_custom = [c for c in conflicts
                    if c["source"] == "custom" and c["command"] != command]
    if other_custom:
        raise ShortcutSetupError(
            "Shortcut already assigned to another Cinnamon custom command. "
            "Reassign it in System Settings → Keyboard → Shortcuts first."
        )
    system = [c for c in conflicts if c["source"] == "builtin"]
    foreign = [c for c in system if (
        c["schema"] != MEDIA_KEYS or c["key"] not in SCREENSHOT_ACTIONS
    )]
    if foreign:
        conflict = foreign[0]
        raise ShortcutSetupError(
            "This key belongs to a Cinnamon desktop/window-manager action "
            f"({conflict['key']}). Reassign it in System Settings → Keyboard first."
        )
    if system and not take_over_screenshot:
        raise ShortcutSetupError(
            "Cinnamon's built-in screenshot action already uses this combination. "
            "Explicit permission is needed before ClipMint can replace it."
        )
    if own and not system:
        return accelerator
    # Preserve every other binding on the same built-in action.
    replacements = [{
        **c,
        "after": [b for b in c["bindings"]
                  if b and _canonical(b) != _canonical(accelerator)],
    } for c in system]
    # GSettings accepts [''] for an unbound accelerator array.
    for change in replacements:
        if not change["after"]:
            change["after"] = [""]
    slot = (None if own else next(
        (f"custom{i}" for i in range(1000) if f"custom{i}" not in current), None
    ))
    if not own and slot is None:
        raise ShortcutSetupError("No unused Cinnamon custom shortcut slot")

    backups = _load_backups() if replacements else []
    backup = {
        "command": command, "accelerator": accelerator,
        "name": name, "slot": own[0]["key"] if own else slot,
        "changes": [{
            "schema": c["schema"], "key": c["key"],
            "before": c["bindings"], "after": c["after"],
        } for c in replacements],
    }
    if replacements and not any(
        entry.get("command") == command and
        _canonical(entry.get("accelerator", "")) == _canonical(accelerator)
        for entry in backups
    ):
        # Persist originals *before* touching Cinnamon.
        _save_backups(backups + [backup])
    try:
        for change in replacements:
            _run("set", change["schema"], change["key"], repr(change["after"]))
        if slot is not None:
            schema = _custom_schema(slot)
            for key, value in (
                ("name", name),
                ("command", command),
                ("binding", repr([accelerator])),
            ):
                _run("set", schema, key, value)
            # Registry commit comes last.
            if _list(_run("get", PARENT, "custom-list")) != current:
                raise ShortcutSetupError("Cinnamon shortcut list changed during setup")
            _run("set", PARENT, "custom-list", repr(current + [slot]))
        final = shortcut_conflicts(sequence)
        if any(c["source"] == "builtin" or
               (c["source"] == "custom" and c["command"] != command)
               for c in final):
            raise ShortcutSetupError(
                "Cinnamon reported another owner after registration; rolled back"
            )
        if not any(c["source"] == "custom" and c["command"] == command
                   for c in final):
            raise ShortcutSetupError(
                "Cinnamon did not activate the ClipMint shortcut; rolled back"
            )
    except Exception:
        # Keep unrelated bindings intact and roll back the changes we made.
        if slot is not None:
            try:
                now = _list(_run("get", PARENT, "custom-list"))
                if slot in now:
                    _run("set", PARENT, "custom-list",
                         repr([x for x in now if x != slot]))
            except ShortcutSetupError:
                pass
        for change in replacements:
            try:
                _run("set", change["schema"], change["key"],
                     repr(change["bindings"]))
            except ShortcutSetupError:
                pass
        raise
    return accelerator


def restore_screenshot_takeover(command: str, sequence: str) -> bool:
    """Restore saved screenshot bindings; never overwrite later user edits."""
    accelerator = cinnamon_accelerator(sequence)
    backups = _load_backups()
    saved = next((
        value for value in backups
        if value.get("command") == command
        and _canonical(value.get("accelerator", "")) == _canonical(accelerator)
    ), None)
    if saved is None:
        return False
    current = _list(_run("get", PARENT, "custom-list"))
    slot = saved["slot"]
    if slot not in current:
        raise ShortcutSetupError(
            "ClipMint's original custom binding is missing; restore via Cinnamon settings"
        )
    schema = _custom_schema(slot)
    if _run("get", schema, "command").strip("'") != command:
        raise ShortcutSetupError("Custom slot has changed; refusing to overwrite it")
    for change in saved["changes"]:
        now = _list(_run("get", change["schema"], change["key"]))
        if now != change["after"]:
            raise ShortcutSetupError(
                "Cinnamon bindings changed since takeover; restore manually"
            )
    _run("set", PARENT, "custom-list",
         repr([item for item in current if item != slot]))
    for change in saved["changes"]:
        _run("set", change["schema"], change["key"], repr(change["before"]))
    _save_backups([v for v in backups if v is not saved])
    return True
