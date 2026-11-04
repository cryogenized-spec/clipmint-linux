"""Opt-in, user-scoped Cinnamon/XDG autostart; never alter system startup."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile

INSTALLED_BINARY = Path("/opt/clipmint/ClipMint")
DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Version=1.0
Name=ClipMint
Comment=Clipboard history and screen capture
Exec=/opt/clipmint/ClipMint --hidden
TryExec=/opt/clipmint/ClipMint
Icon=clipmint
Terminal=false
Categories=Utility;Graphics;
StartupNotify=false
X-GNOME-Autostart-enabled=true
X-ClipMint-Managed=true
"""


class AutostartError(RuntimeError):
    """An existing startup entry or missing executable prevents a safe change."""


def autostart_path(config_home: Path | None = None) -> Path:
    if config_home is None:
        raw = os.environ.get("XDG_CONFIG_HOME", "")
        config_home = Path(raw) if raw and Path(raw).is_absolute() else Path.home() / ".config"
    return Path(config_home) / "autostart" / "clipmint.desktop"


def is_enabled(config_home: Path | None = None) -> bool:
    """Only report an exact entry installed by ClipMint as enabled."""
    path = autostart_path(config_home)
    if path.is_symlink() or not path.is_file():
        return False
    try:
        return path.read_text(encoding="utf-8") == DESKTOP_ENTRY
    except (OSError, UnicodeError):
        return False


def set_enabled(
    enabled: bool,
    config_home: Path | None = None,
    executable: Path = INSTALLED_BINARY,
) -> None:
    """Create/remove only our own desktop file; never overwrite custom entries.

    A complete 0600 temporary file is hard-linked into place atomically, so
    a crash cannot truncate the prior startup configuration. Hard-linking
    refuses to replace an existing path (including a symlink).
    """
    path = autostart_path(config_home)
    exists = path.exists() or path.is_symlink()
    if not enabled:
        if not exists:
            return
        if not is_enabled(config_home):
            raise AutostartError("Existing autostart entry was customized; it was not removed.")
        path.unlink()
        return

    if not Path(executable).is_file():
        raise AutostartError(
            "Install the ClipMint .deb first; /opt/clipmint/ClipMint was not found."
        )
    if exists:
        if is_enabled(config_home):
            return
        raise AutostartError(
            "A custom clipmint.desktop already exists in autostart; it was not overwritten."
        )

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".clipmint-startup-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(DESKTOP_ENTRY)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary_name, path)
        except FileExistsError as exc:
            raise AutostartError("Autostart entry appeared during setup; it was not replaced.") from exc
    finally:
        os.unlink(temporary_name)
