"""Clipboard ingestion service with explicit storage and routing dependencies.

The X11/Qt monitor owns clipboard signals and privacy gates. This service owns
routing, persistence and optional smart-tagging, without widgets or Qt imports.

The store provider is deliberately evaluated for *each* capture: enabling
encrypted history replaces the live store without restarting the window.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from .clipboard_formats import ClipboardEntry
from .smart_types import classify_smart


class CaptureStore(Protocol):
    def add(
        self, kind: str, content: bytes, preview: str, bin_name: str = "Work",
        formats: dict[str, bytes] | None = None,
    ) -> int | None: ...

    def tags(self, clip_id: int) -> list[str]: ...

    def set_tags(self, clip_id: int, values: list[str]) -> None: ...


@dataclass(frozen=True)
class IngestionResult:
    saved_id: int | None
    destination: str | None
    excluded_by_rule: bool = False


class ClipboardIngestionService:
    """Persist a validated ClipboardEntry, using the current live store."""

    def __init__(
        self,
        store_provider: Callable[[], CaptureStore],
        destination_for: Callable[..., str | None],
    ):
        self._store_provider = store_provider
        self._destination_for = destination_for

    def ingest(
        self,
        entry: ClipboardEntry,
        current_bin: str,
        *,
        autosort_enabled: bool,
        preview: str | None = None,
    ) -> IngestionResult:
        full_text = (
            entry.content.decode("utf-8", "replace")
            if entry.kind == "text" else entry.preview
        )
        target = self._destination_for(
            entry.kind, full_text, current_bin, formats=entry.formats,
        )
        if target is None:
            return IngestionResult(None, None, excluded_by_rule=True)

        # Resolve after routing: encrypted-history migration can replace store.
        store = self._store_provider()
        saved_id = store.add(
            entry.kind, entry.content,
            entry.preview if preview is None else preview,
            target, formats=entry.formats,
        )
        if saved_id is not None and autosort_enabled:
            category = classify_smart(entry.kind, full_text, entry.formats)
            if category:
                tag = "type_" + category.replace("-", "_")
                existing = store.tags(saved_id)
                if tag not in existing and len(existing) < 15:
                    store.set_tags(saved_id, [*existing, tag])
        return IngestionResult(saved_id, target)
