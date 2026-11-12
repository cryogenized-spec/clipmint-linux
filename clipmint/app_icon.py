"""Offline, platform-agnostic ClipMint application icon resource.

The shipped PNG is the approved crimson-and-gold ClipMint emblem.
Use the bundled frozen asset on installed builds, the repository asset in
source checkouts, and never request a remote image at runtime.
"""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtGui import QIcon

ICON_RELATIVE = Path("assets") / "icons" / "clipmint.png"


def icon_path() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        bundled = Path(frozen_root) / ICON_RELATIVE
        if bundled.is_file():
            return bundled
    return Path(__file__).resolve().parent.parent / "packaging" / "clipmint.png"


def clipmint_icon() -> QIcon:
    return QIcon(str(icon_path()))
