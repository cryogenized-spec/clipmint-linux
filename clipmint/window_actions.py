"""Window navigation and clipboard reuse actions.

Use the existing window; do not create another store or clipboard monitor.
"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog
from .history_clipboard_copy import copy_saved_clip, CopyOutcome

def view_bin(w) -> str | None:
    """An optional secondary source selector, not a top history tab."""
    name = w.bin_filter.currentData()
    return name if isinstance(name, str) and name in w.store.bins() else None

def active_bin(w) -> str:
    """Writable target for unmatched clips; filter tabs never choose it."""
    return w.view_bin() or "Work"

def new_bin(w):
    name, ok = QInputDialog.getText(w, "New collection", "Collection name:")
    if not ok or not name.strip():
        return
    try:
        w.store.add_bin(name.strip())
    except (ValueError, OSError, Exception) as exc:
        w.error("Collection", str(exc))
        return
    w.bin_filter.addItem(name.strip(), name.strip())
    w.bin_filter.setCurrentIndex(w.bin_filter.count() - 1)

def open_section(w, index: int):
    # Do not rebuild an unchanged secondary page just because its button was
    # clicked again. Clipboard retains its explicit refresh affordance.
    if index != 0 and getattr(w, "_active_section", None) == index:
        return
    w.pages.setCurrentIndex(index)
    w.preview_panel.setVisible(index == 0)
    for i, button in enumerate(w.nav_buttons.values()):
        button.setChecked(index == i)
    w._active_section = index
    if index == 1:
        w.refresh_library_if_changed("Screenshots")
    elif index == 2:
        w.refresh_library_if_changed("Recordings")
    elif index == 0 and not getattr(
        w, "_deferred_initial_history_refresh", False
    ):
        w.refresh()

def _schedule_history_search(w, *_args):
    w._history_search_timer.start()

def copy_selected(w):
    item = w.history.currentItem()
    if item is not None:
        w.copy_clip(item)

def copy_clip(w, item):
    clip_id = item.data(Qt.ItemDataRole.UserRole)
    if copy_saved_clip(
        w.store, lambda: w._own_clipboard_guard,
        QApplication.clipboard, clip_id,
    ) == CopyOutcome.COPIED:
        w.inform("Copied", "Saved snippet copied to the system clipboard")
