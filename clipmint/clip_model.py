"""Clipboard item metadata, categories, and stable sorting definitions.

Pure domain definitions shared by the local store, search service and GUI.
Importing this module never opens SQLite or initializes Qt.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


DEFAULT_BINS = ("Work", "Personal", "Temporary")
SORTS = {
    "Latest first": "touch_seq DESC, id DESC",
    "Oldest first": "touch_seq ASC, id ASC",
    "A–Z": "preview COLLATE NOCASE ASC, id DESC",
    "Z–A": "preview COLLATE NOCASE DESC, id DESC",
    "Numbered list": "touch_seq DESC, id DESC",
}


@dataclass(frozen=True)
class Clip:
    id: int
    kind: str
    preview: str
    pinned: bool
    created_at: str
    bin: str = "Work"
    favorite: bool = False


def classify(clip: Clip) -> str:
    if clip.kind == "files":
        return "Files"
    if clip.kind == "image":
        return "Images"
    text = clip.preview.strip()
    if re.search(r"https?://|www\.", text, flags=re.I):
        return "URLs"
    if re.fullmatch(r"\+?[\d\s()\-.]{7,22}", text) and sum(ch.isdigit() for ch in text) >= 7:
        return "Phone numbers"
    return "Text"


