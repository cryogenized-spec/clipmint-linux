"""Actual Qt Kohaku Gothic Archive screenshots using the approved, packaged card.

This is test-only synthetic data. It never touches the user's clipboard history.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication
from clipmint.app import ClipMintWindow


def sample_image() -> bytes:
    pic = QImage(640, 360, QImage.Format.Format_ARGB32)
    pic.fill(QColor("#17131C"))
    painter = QPainter(pic)
    painter.fillRect(80, 50, 480, 255, QColor("#3D2934"))
    painter.fillRect(80, 50, 480, 52, QColor("#9E2D4A"))
    painter.setPen(QColor("#F4EEEB"))
    painter.drawText(115, 82, "CLIPMINT / SCREEN CAPTURE")
    for x, hue in ((116,"#482C40"),(255,"#9A435D"),(396,"#575C4B")):
        painter.fillRect(x, 140, 107, 140, QColor(hue))
    painter.end()
    data=QByteArray()
    buffer=QBuffer(data)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert pic.save(buffer,"PNG")
    buffer.close()
    return bytes(data)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m tools.render_crimson_review OUTPUT_DIRECTORY")
    destination=Path(sys.argv[1]).resolve()
    destination.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix="clipmint-qa-") as root:
        os.environ["XDG_DATA_HOME"]=root
        app=QApplication([])
        app.setQuitOnLastWindowClosed(False)
        window=ClipMintWindow()
        if not window.manga_dock.has_card_art:
            raise RuntimeError("Approved Kohaku card missing: screenshot would show fallback art")
        window.monitoring=False
        window.store.add("text",b"Inspection notes - workshop","Inspection notes - workshop")
        window.store.add("text",b"https://example.org/clipmint","https://example.org/clipmint")
        window.store.add("text",b"sudo apt update && sudo apt upgrade","sudo apt update && sudo apt upgrade")
        window.store.add("text",b"#D93657","#D93657")
        imgid=window.store.add("image",sample_image(),"Screenshot example 640 x 360")
        window.refresh()

        def capture():
            for width,height,name in [
                (1500,920,"kohaku-qt-desktop.png"),
                (1100,880,"kohaku-qt-laptop.png")
            ]:
                window.resize(width,height)
                window.show()
                app.processEvents()
                # Select known synthetic screenshot, which drives the real preview pane.
                for i in range(window.history.count()):
                    item=window.history.item(i)
                    if item.data(256)==imgid:
                        window.history.setCurrentItem(item)
                        break
                app.processEvents()
                result=window.grab()
                output=destination/name
                if result.isNull() or not result.save(str(output),"PNG"):
                    raise RuntimeError("Unable to render "+str(output))
                print(f"Capture {output}: {result.width()}x{result.height()}",flush=True)
            window.monitoring=False
            app.exit(0)

        QTimer.singleShot(550,capture)
        outcome=app.exec()
        window.store.close()
        if outcome:
            raise SystemExit(outcome)


if __name__ == "__main__":
    main()
