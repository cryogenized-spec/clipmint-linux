"""Local text operations, explicit snippet templates, and a manual paste queue.

No shell commands, external requests, executable templates or automatic typing.
A user explicitly chooses each queued item to copy to the system clipboard.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote, unquote

MAX_TRANSFORM_BYTES = 1024 * 1024
_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z][a-zA-Z0-9_]{0,39})\s*\}\}")

TRANSFORMS = (
    "Strip outer whitespace",
    "Trim each line",
    "Remove empty lines",
    "Deduplicate lines",
    "Sort lines A–Z",
    "Uppercase",
    "Lowercase",
    "Title case",
    "Format JSON",
    "Compact JSON",
    "URL encode",
    "URL decode",
)


def template_fields(body: str) -> list[str]:
    """Identify distinct placeholders without evaluating template expressions."""
    return list(dict.fromkeys(_PLACEHOLDER.findall(body)))


def render_template(body: str, values: dict[str, str]) -> str:
    fields = template_fields(body)
    missing = [name for name in fields if name not in values]
    if missing:
        raise ValueError("Missing template fields: " + ", ".join(missing))
    result = _PLACEHOLDER.sub(lambda match: values[match.group(1)], body)
    if len(result.encode("utf-8")) > MAX_TRANSFORM_BYTES:
        raise ValueError("Filled template exceeds 1 MiB")
    return result


def transform_text(text: str, operation: str) -> str:
    """Return text for explicit user review, never modify a saved entry."""
    if len(text.encode("utf-8")) > MAX_TRANSFORM_BYTES:
        raise ValueError("Text exceeds the 1 MiB transformation limit")
    if operation == "Strip outer whitespace":
        result = text.strip()
    elif operation == "Trim each line":
        result = "\n".join(line.strip() for line in text.splitlines())
    elif operation == "Remove empty lines":
        result = "\n".join(line for line in text.splitlines() if line.strip())
    elif operation == "Deduplicate lines":
        result = "\n".join(dict.fromkeys(text.splitlines()))
    elif operation == "Sort lines A–Z":
        result = "\n".join(sorted(text.splitlines(), key=str.casefold))
    elif operation == "Uppercase":
        result = text.upper()
    elif operation == "Lowercase":
        result = text.lower()
    elif operation == "Title case":
        result = text.title()
    elif operation == "Format JSON":
        result = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    elif operation == "Compact JSON":
        result = json.dumps(json.loads(text), ensure_ascii=False, separators=(",", ":"))
    elif operation == "URL encode":
        result = quote(text, safe="")
    elif operation == "URL decode":
        result = unquote(text)
    else:
        raise ValueError("Unknown text transformation")
    if len(result.encode("utf-8")) > MAX_TRANSFORM_BYTES:
        raise ValueError("Transformed text exceeds 1 MiB")
    return result


class PasteQueue:
    """Explicit one-at-a-time clipboard queue; IDs, not raw secrets, in memory."""

    def __init__(self, limit: int = 30):
        self.limit = limit
        self._items: list[int] = []

    def add(self, clip_id: int) -> bool:
        if not isinstance(clip_id, int) or clip_id <= 0:
            raise ValueError("Invalid clipboard ID")
        if clip_id in self._items:
            return False
        if len(self._items) >= self.limit:
            raise ValueError(f"Paste queue supports at most {self.limit} entries")
        self._items.append(clip_id)
        return True

    def next_id(self) -> int | None:
        return self._items.pop(0) if self._items else None

    def clear(self) -> None:
        self._items.clear()

    def __len__(self):
        return len(self._items)

    def ids(self) -> tuple[int, ...]:
        return tuple(self._items)
