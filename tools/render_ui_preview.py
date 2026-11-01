"""Capture an actual ClipMint QWidget render using safe, synthetic sample history."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from clipmint.app import ClipMintWindow


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/render_ui_preview.py OUTPUT.png")
    outfile = Path(sys.argv[1]).resolve()
    outfile.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="clipmint-ui-preview-") as root:
        os.environ["XDG_DATA_HOME"] = root
        app = QApplication([])
        window = ClipMintWindow()
        window.store.add("text", b"Project notes: ClipMint layout ideas", "Project notes: ClipMint layout ideas")
        window.store.add("text", b"Screenshot area - mouse selection", "Screenshot area - mouse selection")
        window.store.add("text", b"Record selected frame, save MP4", "Record selected frame, save MP4")
        window.store.add("text", b"Right click a snippet to Copy it", "Right click a snippet to Copy it")
        window.store.add("text", b"Pin useful snippets for later", "Pin useful snippets for later")
        window.store.pin(1, True)
        window.refresh()
        window.show()
        window.activateWindow()

        def capture():
            app.processEvents()
            pixelmap = window.grab()
            if pixelmap.isNull() or not pixelmap.save(str(outfile), "PNG"):
                print("Could not capture ClipMint Qt widget", file=sys.stderr)
                app.exit(1)
                return
            print(f"Screenshot created: {outfile}, {pixelmap.width()} x {pixelmap.height()}", flush=True)
            # A one-shot CI renderer. Avoid Qt's Xvfb teardown path.
            os._exit(0)

        QTimer.singleShot(700, capture)
        code = app.exec()
        window.store.close()
        if code:
            raise SystemExit(code)


if __name__ == "__main__":
    main()
