"""Native X11-compatible, privacy-aware drag source for saved history.

Text is dragged as text (and recognised HTTP(S) URLs as links); stored file
lists retain their URI MIME formats. Images provide both PNG/image MIME and a
short-lived owner-only PNG path for applications accepting file uploads.

Drag does not modify the system clipboard, start a subprocess or bypass the
normal history/keyring privacy boundaries. A successful image drop keeps the
temporary file briefly for consumers that read the URI asynchronously.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QAbstractItemView, QListWidget

from .clipboard_formats import mime_from_entry, sensitive_payload

MAX_DRAG_IMAGE_BYTES = 16 * 1024 * 1024
MAX_DRAG_IMAGE_PIXELS = 32_000_000
IMAGE_DRAG_RETENTION_MS = 120_000


def _valid_png(content: bytes) -> bool:
    """Reject oversized/invalid bitmap payloads before any Qt decoding."""
    if (not 0 < len(content) <= MAX_DRAG_IMAGE_BYTES
            or len(content) < 24
            or not content.startswith(b"\x89PNG\r\n\x1a\n")):
        return False
    width = int.from_bytes(content[16:20], "big")
    height = int.from_bytes(content[20:24], "big")
    return bool(width and height and width * height <= MAX_DRAG_IMAGE_PIXELS)


def build_history_drag_mime(store, clip_id: int):
    """Return (QMimeData, TemporaryDirectory | None), or None if disallowed.

    The returned temporary directory remains the caller's responsibility
    until after the drop finishes and external readers have had time to
    accept a file URI.
    """
    entry = store.get(clip_id)
    if entry is None:
        return None
    kind, content = entry
    if kind not in ("text", "image", "files") or not isinstance(content, bytes):
        return None
    formats = store.get_formats(clip_id) or {}
    if sensitive_payload(kind, content, formats):
        return None
    if kind == "image" and not _valid_png(content):
        return None

    # Reuse exactly the supported MIME formats from the existing, audited
    # history copy boundary. The source clipboard is not altered.
    mime = mime_from_entry(kind, content, formats)
    temporary = None
    if kind == "image":
        if not mime.hasImage():
            return None
        temporary = TemporaryDirectory(prefix="clipmint-image-drop-")
        try:
            path = Path(temporary.name) / "clipboard-image.png"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            with os.fdopen(os.open(path, flags, 0o600), "wb") as handle:
                handle.write(content)
            mime.setUrls([QUrl.fromLocalFile(str(path))])
        except OSError:
            temporary.cleanup()
            return None
    elif kind == "text":
        value = content.decode("utf-8", "replace").strip()
        if value and value == content.decode("utf-8", "replace"):
            link = QUrl(value)
            if (link.isValid() and link.scheme().lower() in ("http", "https")
                    and bool(link.host())):
                mime.setUrls([link])
    return mime, temporary


class HistoryDragList(QListWidget):
    """A CopyAction-only drag source for saved clipboard items."""

    def __init__(self, owner):
        super().__init__(owner)
        self._drag_owner = owner
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def startDrag(self, supported_actions):
        owner = self._drag_owner
        if (getattr(owner, "_closing", False)
                or getattr(owner, "history_security_error", "")
                or getattr(owner.store, "closed", False)):
            return
        item = self.currentItem()
        if item is None:
            return
        clip_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(clip_id, int):
            return
        try:
            payload = build_history_drag_mime(owner.store, clip_id)
        except (OSError, ValueError, RuntimeError):
            # Locked/corrupt/missing rows cannot become a drag payload.
            return
        if payload is None:
            return
        mime, temporary = payload
        drag = QDrag(self)
        drag.setMimeData(mime)
        try:
            result = drag.exec(Qt.DropAction.CopyAction)
        finally:
            if temporary is not None:
                if result == Qt.DropAction.CopyAction:
                    # Some browser upload targets read a dropped file URI
                    # after the drag loop has completed.
                    QTimer.singleShot(IMAGE_DRAG_RETENTION_MS, temporary.cleanup)
                else:
                    temporary.cleanup()
