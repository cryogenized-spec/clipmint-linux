"""Real Qt screenshots of the Crimson Archive layout for comparison with v2 HTML.

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
from clipmint.organizer_ui import TemplatesDialog


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
        window.monitoring=False
        report_id=window.store.add(
            "text", b"Inspection report: detailed bench record with a special "
                    b"torque wrench calibration diagnostic in the complete body",
            "Workshop inspection summary"
        )
        window.store.favorite(report_id, True)
        window.store.set_tags(report_id, ["workshop", "priority"])
        window.store.add("text",b"Inspection notes - workshop","Inspection notes - workshop")
        window.store.add("text",b"https://example.org/clipmint","https://example.org/clipmint")
        window.store.add("text",b"sudo apt update && sudo apt upgrade","sudo apt update && sudo apt upgrade")
        window.store.add("text",b"#D93657","#D93657")
        imgid=window.store.add("image",sample_image(),"Screenshot example 640 x 360")
        window.refresh()

        def capture():
            for width,height,name in [
                (1500,920,"crimson-qt-desktop.png"),
                (1100,880,"crimson-qt-laptop.png")
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
            # Prove an FTS-only body match works through real Qt controls,
            # with tag and favourite filtering rather than a static mockup.
            window.resize(1500,920)
            window.search.setText("torque wrench")
            window.sort_combo.setCurrentIndex(
                window.sort_combo.findData("Best match")
            )
            window.favorites_filter.setChecked(True)
            tag_index=window.tag_filter.findData("workshop")
            assert tag_index >= 0
            window.tag_filter.setCurrentIndex(tag_index)
            app.processEvents()
            assert window.history.count()==1, "Indexed body search did not reach GUI"
            window.history.setCurrentRow(0)
            app.processEvents()
            target=destination/"kohaku-qt-indexed-search.png"
            assert window.grab().save(str(target),"PNG")
            print(f"Capture {target}: full-text + tags + favourites",flush=True)

            # Render the actual editor, not a flattened template screenshot.
            window.store.save_template("Customer follow-up",
                "Hello {{customer}}, your repair is ready for collection.")
            dlg=TemplatesDialog(window.store, lambda _: None, window)
            dlg.reload(selected=window.store.templates()[0][0])
            dlg.show()
            app.processEvents()
            target=destination/"kohaku-qt-snippets.png"
            assert dlg.grab().save(str(target),"PNG")
            print(f"Capture {target}: live reusable snippets editor",flush=True)
            dlg.close()
            window.monitoring=False
            app.exit(0)

        QTimer.singleShot(550,capture)
        outcome=app.exec()
        window.store.close()
        if outcome:
            raise SystemExit(outcome)


if __name__ == "__main__":
    main()
