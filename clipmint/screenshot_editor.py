"""Open a captured PNG in a real installed image editor when available.

Never run a shell or interpret user-controlled clipboard/filename as code.
If no editor is available, use the user's system PNG association and disclose
that this may be a viewer rather than an editor.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

EDITOR_CHOICES = (
    ("pinta", "Pinta"),
    ("gimp", "GIMP"),
    ("krita", "Krita"),
    ("drawing", "Drawing"),
    ("kolourpaint", "KolourPaint"),
)


def installed_editors(which=shutil.which) -> list[tuple[str, str]]:
    return [(key, label) for key, label in EDITOR_CHOICES if which(key)]


def resolve_editor(preference: str = "auto", which=shutil.which) -> tuple[list[str], str, bool]:
    """Return argv prefix, display name and a true-editor flag."""
    found = installed_editors(which)
    options = dict(EDITOR_CHOICES)
    if preference not in ("auto", "system") and preference in options:
        if not which(preference):
            raise FileNotFoundError(f"Configured editor {options[preference]} is not installed")
        return [preference], options[preference], True
    if preference == "auto" and found:
        return [found[0][0]], found[0][1], True
    if not which("xdg-open"):
        raise FileNotFoundError("No image editor or system image opener found")
    return ["xdg-open"], "system image application", False


def open_image_editor(
    path: Path, preference: str = "auto", which=shutil.which,
    popen=subprocess.Popen,
) -> tuple[str, bool]:
    image = Path(path)
    if not image.is_file() or image.suffix.lower() != ".png":
        raise FileNotFoundError("Screenshot is no longer available")
    argv, display, is_editor = resolve_editor(preference, which=which)
    popen(
        argv + [str(image)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return display, is_editor
