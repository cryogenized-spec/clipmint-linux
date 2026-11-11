"""Responsive archive layout, separated from application lifetime."""
from __future__ import annotations

def update_manga_visibility(w):
    """Keep dock labels readable; never regress to an icons-only rail.

    The character card hides on compact displays so real editing and the
    selected-item preview retain useful width.
    """
    show = w.width() >= 1120 and w.height() >= 700
    w.manga_dock.setVisible(show)
    if show:
        w.manga_dock.setFixedWidth(
            min(390, max(310, int(w.width() * .265)))
        )
    wide = w.width() >= 1180
    w.dock_panel.setFixedWidth(142 if wide else 134)
    if hasattr(w, "archive_heading"):
        w.archive_heading.setText(
            "Clipboard  ·  クリップボード"
            if w.width() >= 1150 else "Clipboard"
        )
    if hasattr(w, "preview_heading"):
        w.preview_heading.setText(
            "プレビュー  Preview"
            if w.width() >= 1190 else "プレビュー"
        )
    for label, button in w.nav_buttons.items():
        display = button.property("dockDisplay") or label
        subtitle = button.property("dockSubtitle") or ""
        icon = button.property("dockIcon") or "◇"
        # Even in the compact layout titles remain visible.
        button.setText(
            f"{icon}  {display}\n   {subtitle}"
            if wide else f"{icon}  {display}"
        )
        button.setMinimumHeight(67 if wide else 49)
        button.setToolTip(f"{display}: {label}")
