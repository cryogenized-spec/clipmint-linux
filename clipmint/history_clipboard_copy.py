"""Single clipboard-copy boundary for SAVED ClipMint history entries.

This is deliberately distinct from the encrypted vault's ephemeral copy path.
The providers are invoked only after a valid, compatible stored entry exists,
so rejected requests never touch the clipboard or arm an own-write guard.

Temporary TTL is refreshed only after the clipboard write succeeds.
"""
from __future__ import annotations

from enum import Enum
from typing import Callable

from .clipboard_formats import mime_from_entry


class CopyOutcome(str, Enum):
    COPIED = "copied"
    MISSING = "missing"
    TEXT_ONLY = "text_only"


def copy_saved_clip(
    store,
    guard_provider: Callable,
    clipboard_provider: Callable,
    clip_id: int,
    *,
    plain: bool = False,
) -> CopyOutcome:
    """Copy a saved clip to the system clipboard without creating a new clip."""
    entry = store.get(clip_id)
    if entry is None:
        return CopyOutcome.MISSING
    kind, content = entry
    if plain and kind != "text":
        return CopyOutcome.TEXT_ONLY

    if plain:
        value = content.decode("utf-8", "replace")
        guard_provider().note_text(value)
        clipboard_provider().setText(value)
    else:
        # Build MIME data before mutating the guard or clipboard. A malformed
        # history payload must never leave a phantom own-write expectation.
        mime_data = mime_from_entry(kind, content, store.get_formats(clip_id))
        guard_provider().note_entry(kind, content)
        clipboard_provider().setMimeData(mime_data)
    store.refresh_temporary_copy_time(clip_id)
    return CopyOutcome.COPIED
