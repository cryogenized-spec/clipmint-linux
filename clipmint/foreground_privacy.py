"""Supplemental foreground-app privacy exclusion for Cinnamon/X11.

X11 cannot prove the true clipboard owner from the active-window class.
This is only a useful best-effort blocklist, not a security boundary.
"""
from __future__ import annotations
import subprocess
import shutil
from .quick_popup import active_window

DEFAULT_BLOCKED = ("keepassxc", "1password", "bitwarden")


def blocked_foreground(patterns: str, window_lookup=active_window) -> bool:
    _wid, klass = window_lookup()
    if not klass:
        return False
    terms = [line.strip().casefold() for line in patterns.replace(",", "\n").splitlines()]
    return any(term in klass for term in terms if len(term) >= 3)
