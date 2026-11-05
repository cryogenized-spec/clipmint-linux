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
