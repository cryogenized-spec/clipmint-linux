"""Only suppress clipboard events whose content matches our own write."""
from __future__ import annotations
import hashlib


class OwnClipboardGuard:
    def __init__(self):
        self.expected: tuple[str, object] | None = None

    def note_text(self, value: str) -> None:
        self.expected = ("text", value)

    def note_entry(self, kind: str, content: bytes) -> None:
        if kind == "text":
            self.note_text(content.decode("utf-8", "replace"))
        else:
            self.expected = (kind, hashlib.sha256(content).digest())

    def consume(self, mime) -> bool:
        expected = self.expected
        self.expected = None
        if expected is None or mime is None:
            return False
        kind, value = expected
        try:
            if kind == "text":
                return mime.hasText() and mime.text() == value
            if kind == "image":
                return (mime.hasFormat("image/png") and
                        hashlib.sha256(bytes(mime.data("image/png"))).digest() == value)
            if kind == "files":
                for fmt in ("x-special/gnome-copied-files", "text/uri-list"):
                    if (mime.hasFormat(fmt) and
                            hashlib.sha256(bytes(mime.data(fmt))).digest() == value):
                        return True
        except (RuntimeError, ValueError, TypeError):
            return False
        return False


class HiddenTextClipboardProbe:
    """Memory-only guard for lost X11 text-change notifications.

    Qt normally delivers QClipboard.dataChanged, but some desktop clipboard
    managers can interfere with X11 ownership notifications. A lightweight
    hidden-window timer can compare the current plain-text contents and route
    *new* values through the same privacy-aware capture handler.

    This stores only a digest, not copied text. It deliberately does not poll
    bitmap image data: repeatedly decoding large images would be expensive.
    """

    def __init__(self):
        self.last: bytes | None = None

    def observe(self, mime) -> bool:
        if mime is None or not mime.hasText():
            changed = self.last is not None
            self.last = None
            return changed
        text = mime.text()
        # The normal MIME importer rejects text above 2 MiB; do not spend
        # time hashing oversized clipboard payloads on a periodic probe.
        if len(text) > 2 * 1024 * 1024:
            self.last = None
            return False
        current = hashlib.blake2b(text.encode("utf-8"), digest_size=16).digest()
        changed = current != self.last
        self.last = current
        return changed
