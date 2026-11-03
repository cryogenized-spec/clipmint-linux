"""Clipboard format preservation and bounded, fail-closed sensitivity checks.

X11 MIME source hints are untrusted and incomplete: app/window-based blocklists
are supplemental heuristics and never a guarantee against secret capture.
"""
from __future__ import annotations
import base64
import json
import re
from dataclasses import dataclass

ALLOWED = (
    "text/plain", "text/plain;charset=utf-8", "text/html",
    "text/uri-list", "x-special/gnome-copied-files", "image/png",
)
MAX_FORMAT_BYTES = 16 * 1024 * 1024
MAX_BUNDLE_BYTES = 20 * 1024 * 1024
SECRET_HINT = "x-kde-passwordManagerHint"
DENIED_MIME_PARTS = ("keepassxc", "bitwarden", "1password", "passwordmanager", "password-manager")


def is_concealed(mime) -> bool:
    formats = [f.lower() for f in mime.formats()]
    if any(any(s in f for s in DENIED_MIME_PARTS) for f in formats):
        return True
    # Prefer over-exclusion to storing a password-manager clipboard.
    for name in mime.formats():
        if name.lower() == SECRET_HINT.lower():
            data = bytes(mime.data(name)).strip().lower()
            return data in (b"secret", b"true", b"1") or not data
    return False


def luhn(value: str) -> bool:
    digits = [int(c) for c in value if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2:
            digit *= 2
            if digit > 9: digit -= 9
        total += digit
    return total % 10 == 0


def sensitive_text(value: str) -> bool:
    """Conservative broad screening; false negatives are still possible."""
    if re.search(r"(?i)(?:password|passwd|api[_ -]?key|secret|access[_ -]?token|"
                 r"authorization|bearer|private[_ -]?key)\s*[:=]\s*\S+", value):
        return True
    if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", value):
        return True
    if re.search(r"(?i)\b(?:sk-[\w-]{18,}|gh[pousr]_[A-Za-z0-9_]{18,}|"
                 r"AKIA[A-Z0-9]{16})\b", value):
        return True
    for match in re.finditer(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)", value):
        if luhn(match.group()):
            return True
    return False


@dataclass(frozen=True)
class ClipboardEntry:
    kind: str
    content: bytes
    preview: str
    formats: dict[str, bytes]


def bundle_to_bytes(formats: dict[str, bytes]) -> bytes:
    data = {key: base64.b64encode(value).decode("ascii") for key,value in formats.items()
            if key in ALLOWED}
    return json.dumps(data, separators=(",", ":")).encode("ascii")


def bundle_from_bytes(raw: bytes | None) -> dict[str, bytes]:
    if not raw: return {}
    if len(raw) > MAX_BUNDLE_BYTES * 1.5:
        return {}
    try:
        result = json.loads(raw)
        if not isinstance(result, dict): return {}
        decoded = {name: base64.b64decode(value, validate=True) for name,value in result.items()
                   if name in ALLOWED and isinstance(value, str)}
        if sum(len(value) for value in decoded.values()) > MAX_BUNDLE_BYTES:
            return {}
        return decoded
    except (ValueError, TypeError, KeyError):
        return {}


def from_mime(mime, png: bytes | None = None) -> ClipboardEntry | None:
    """Capture a safe MIME subset; never decode unknown clipboard objects."""
    if is_concealed(mime):
        return None
    saved: dict[str, bytes] = {}
    total = 0
    for name in mime.formats():
        if name not in ALLOWED:
            continue
        value = bytes(mime.data(name))
        if len(value) > MAX_FORMAT_BYTES or total + len(value) > MAX_BUNDLE_BYTES:
            return None  # fail closed, don't silently lose rich formats
        total += len(value)
        saved[name] = value
    if png:
        previous = saved.get("image/png", b"")
        if len(png) > MAX_FORMAT_BYTES or (total - len(previous) + len(png)) > MAX_BUNDLE_BYTES:
            return None
        saved["image/png"] = png
    if mime.hasUrls() or "x-special/gnome-copied-files" in saved:
        uri_raw = saved.get("x-special/gnome-copied-files") or saved.get("text/uri-list", b"")
        text = uri_raw.decode("utf-8", errors="replace")
        paths = [ln for ln in text.splitlines() if ln and ln not in ("copy","cut") and not ln.startswith("#")]
        if not paths: return None
        return ClipboardEntry("files", uri_raw, f"{len(paths)} file(s): " + paths[0][:450], saved)
    if png:
        # The PNG is already stored in the entry's content. Avoid writing a
        # redundant 16 MB image into its auxiliary MIME bundle as well.
        return ClipboardEntry("image", png, "",
                              {key:value for key,value in saved.items() if key != "image/png"})
    text = mime.text() if mime.hasText() else ""
    if not text.strip() and "text/html" in saved:
        # Preserve HTML only when a safe/plain textual representation is present.
        return None
    if text.strip():
        raw = text.encode("utf-8")
        if len(raw) > 2 * 1024 * 1024 or sensitive_text(text):
            return None
        if "text/html" in saved and sensitive_text(saved["text/html"].decode("utf-8", "replace")):
            return None
        if "text/plain" not in saved and "text/plain;charset=utf-8" not in saved:
            saved["text/plain;charset=utf-8"] = raw
        return ClipboardEntry("text", raw, " ".join(text.split())[:550], saved)
    return None


def mime_from_entry(kind: str, content: bytes, formats: dict[str, bytes]):
    from PySide6.QtCore import QMimeData
    from PySide6.QtGui import QImage
    mime = QMimeData()
    for name, data in formats.items():
        if name in ALLOWED:
            mime.setData(name, data)
    if kind == "image":
        if not mime.hasFormat("image/png"):
            mime.setData("image/png", content)
        image = QImage.fromData(content, "PNG")
        if not image.isNull():
            mime.setImageData(image)
    elif kind == "files":
        if not formats: mime.setData("text/uri-list", content)
    elif kind == "text":
        if not (mime.hasFormat("text/plain") or mime.hasFormat("text/plain;charset=utf-8")):
            mime.setText(content.decode("utf-8", "replace"))
    return mime
