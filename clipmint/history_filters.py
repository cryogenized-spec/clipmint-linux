"""Clipboard timeline tabs are view filters, never physical storage bins.

Autosort destinations and manually managed collections are independent of the
top tab bar. A filter selection must never move or rewrite a stored clip.
"""
from __future__ import annotations

# Label and ClipStore.search(category=...) value.
HISTORY_FILTERS: tuple[tuple[str, str], ...] = (
    ("All clips", "All"),
    ("Text", "Text"),
    ("Links", "URLs"),
    ("Phone numbers", "Phone numbers"),
    ("Images", "Images"),
    ("Files", "Files"),
)

VALID_CATEGORIES = frozenset(category for _label, category in HISTORY_FILTERS)


def populate_filter_tabs(tabs) -> None:
    """Install static category views; no call to store.bins()."""
    for label, category in HISTORY_FILTERS:
        index = tabs.addTab(label)
        tabs.setTabData(index, category)
    tabs.setCurrentIndex(0)


def selected_category(tabs) -> str:
    """Map the current tab to a safe category for ordinary/encrypted search."""
    selected = tabs.tabData(tabs.currentIndex())
    return selected if selected in VALID_CATEGORIES else "All"
