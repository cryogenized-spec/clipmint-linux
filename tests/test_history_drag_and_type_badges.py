"""Native saved-history drag MIME and always-visible type badge contracts.

Uses synthetic text/images, and never drops into a real browser or reads a
personal clipboard database. Physical Cinnamon X11 upload testing remains a
release acceptance gate.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QListWidget, QListWidgetItem,
    QStyleOptionViewItem, QWidget,
)

from clipmint.crimson_widgets import CrimsonClipDelegate, badge_title
from clipmint.history_drag import (
    HistoryDragList, IMAGE_DRAG_RETENTION_MS,
    build_history_drag_mime, _valid_png,
)


def png_fixture() -> bytes:
    image = QImage(12, 8, QImage.Format.Format_RGB32)
    image.fill(QColor("#C0607C"))
    buffer = QByteArray()
    stream = QBuffer(buffer)
    assert stream.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(stream, "PNG")
    stream.close()
    return bytes(buffer)


def fake_store(kind: str, content: bytes, formats=None):
    return SimpleNamespace(
        closed=False,
        get=Mock(return_value=(kind, content)),
        get_formats=Mock(return_value=formats or {}),
    )


class HistoryTypeBadgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_badge_labels_are_human_readable(self):
        expected = {
            "IMG": "IMAGE", "TXT": "TEXT", "URL": "LINK",
            "FILE": "FILES", "HEX": "HEX", "CODE": "CODE",
        }
        for kind, title in expected.items():
            self.assertEqual(badge_title(kind), title)

    def test_badge_painted_even_when_optional_icons_are_disabled(self):
        for kind, preview, colour in (
            ("image", "Image 12 × 8", "#D34D70"),
            ("text", "ordinary sentence", "#D8D0CE"),
            ("text", "https://example.org", "#91B3B0"),
            ("files", "1 file", "#DEC3A7"),
        ):
            with self.subTest(kind=kind, preview=preview):
                listing = QListWidget()
                item = QListWidgetItem(preview)
                item.setData(int(Qt.ItemDataRole.UserRole) + 1, {
                    "kind": kind, "raw_preview": preview,
                    "preview": preview, "show_badges": False,
                })
                listing.addItem(item)
                image = QImage(430, 77, QImage.Format.Format_RGB32)
                image.fill(QColor("#000000"))
                option = QStyleOptionViewItem()
                option.rect = QRect(0, 0, 430, 77)
                painter = QPainter(image)
                try:
                    CrimsonClipDelegate(listing).paint(
                        painter, option, listing.model().index(0, 0)
                    )
                finally:
                    painter.end()
                    listing.deleteLater()
                # Left edge of the rectangular type chip, outside glyphs.
                self.assertEqual(image.pixelColor(17, 18), QColor(colour))


class HistoryDragMimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_full_length_unicode_text_and_html_preserved_without_clipboard_write(self):
        text = "long field payload\n" + ("☕ abcde" * 1600)
        store = fake_store("text", text.encode("utf-8"),
                           {"text/html": b"<p>long field payload</p>"})
        board = QApplication.clipboard()
        board.setText("untouched external clipboard")
        result = build_history_drag_mime(store, 31)
        self.assertIsNotNone(result)
        mime, temporary = result
        self.assertIsNone(temporary)
        self.assertEqual(mime.text(), text)
        self.assertIn("<p>long field payload</p>", mime.html())
        self.assertFalse(mime.hasUrls())
        self.assertEqual(board.text(), "untouched external clipboard")
        store.get.assert_called_once_with(31)
        store.get_formats.assert_called_once_with(31)

    def test_http_link_exposes_native_url_and_plain_text(self):
        url = "https://example.org/upload?type=picture"
        mime, temporary = build_history_drag_mime(
            fake_store("text", url.encode()), 12
        )
        self.assertIsNone(temporary)
        self.assertEqual(mime.text(), url)
        self.assertTrue(mime.hasUrls())
        self.assertEqual(mime.urls()[0].toString(), url)

    def test_saved_file_uri_bundle_preserved(self):
        uri = b"file:///tmp/synthetic-document.txt\n"
        mime, temporary = build_history_drag_mime(
            fake_store("files", uri, {"text/uri-list": uri}), 3
        )
        self.assertIsNone(temporary)
        self.assertEqual(bytes(mime.data("text/uri-list")), uri)

    def test_png_has_image_mime_and_usable_owner_only_upload_file(self):
        raw = png_fixture()
        payload = build_history_drag_mime(fake_store("image", raw), 77)
        self.assertIsNotNone(payload)
        mime, temporary = payload
        try:
            self.assertTrue(mime.hasImage())
            self.assertEqual(bytes(mime.data("image/png")), raw)
            self.assertTrue(mime.hasUrls())
            self.assertEqual(len(mime.urls()), 1)
            filename = Path(mime.urls()[0].toLocalFile())
            self.assertTrue(filename.is_file())
            self.assertEqual(filename.read_bytes(), raw)
            self.assertEqual(filename.stat().st_mode & 0o777, 0o600)
            self.assertEqual(filename.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(mime.imageData().size().width(), 12)
        finally:
            folder = Path(temporary.name)
            temporary.cleanup()
        self.assertFalse(folder.exists())

    def test_absent_sensitive_or_invalid_entry_never_creates_drop(self):
        self.assertIsNone(build_history_drag_mime(
            SimpleNamespace(get=lambda _id: None), 99
        ))
        with patch("clipmint.history_drag.sensitive_payload", return_value=True):
            store = fake_store("text", b"secret fixture")
            self.assertIsNone(build_history_drag_mime(store, 4))
            store.get_formats.assert_called_once_with(4)
        self.assertIsNone(build_history_drag_mime(
            fake_store("image", b"not a png"), 5
        ))
        malicious_dimensions = (
            b"\x89PNG\r\n\x1a\n" + b"\0"*8
            + (100000).to_bytes(4, "big")
            + (100000).to_bytes(4, "big")
        )
        self.assertFalse(_valid_png(malicious_dimensions))

    def test_widget_is_copy_only_drag_source_and_never_modifies_clipboard(self):
        owner = QWidget()
        owner.store = fake_store("text", b"drag me into a text input")
        owner.history_security_error = ""
        owner._closing = False
        listing = HistoryDragList(owner)
        try:
            self.assertTrue(listing.dragEnabled())
            self.assertEqual(
                listing.dragDropMode(), QAbstractItemView.DragDropMode.DragOnly
            )
            item = QListWidgetItem("drag me")
            item.setData(Qt.ItemDataRole.UserRole, 16)
            listing.addItem(item)
            listing.setCurrentItem(item)
            board = QApplication.clipboard()
            board.setText("original clipboard")
            with patch("clipmint.history_drag.QDrag") as drag:
                drag.return_value.exec.return_value = Qt.DropAction.CopyAction
                listing.startDrag(Qt.DropAction.CopyAction)
                drag.return_value.setMimeData.assert_called_once()
                mime = drag.return_value.setMimeData.call_args.args[0]
                self.assertEqual(mime.text(), "drag me into a text input")
                drag.return_value.exec.assert_called_once_with(
                    Qt.DropAction.CopyAction
                )
            self.assertEqual(board.text(), "original clipboard")
            owner.history_security_error = "Keyring unavailable"
            with patch("clipmint.history_drag.QDrag") as drag:
                listing.startDrag(Qt.DropAction.CopyAction)
                drag.assert_not_called()
        finally:
            listing.deleteLater()
            owner.deleteLater()

    def test_successful_png_drag_retains_upload_file_until_timer_cleanup(self):
        owner = QWidget()
        owner.store = fake_store("image", png_fixture())
        owner.history_security_error = ""
        owner._closing = False
        listing = HistoryDragList(owner)
        try:
            item = QListWidgetItem("Screenshot image")
            item.setData(Qt.ItemDataRole.UserRole, 10)
            listing.addItem(item)
            listing.setCurrentItem(item)
            with patch("clipmint.history_drag.QDrag") as drag, patch(
                "clipmint.history_drag.QTimer.singleShot"
            ) as timer:
                drag.return_value.exec.return_value = Qt.DropAction.CopyAction
                listing.startDrag(Qt.DropAction.CopyAction)
                mime = drag.return_value.setMimeData.call_args.args[0]
                filename = Path(mime.urls()[0].toLocalFile())
                self.assertTrue(filename.exists())
                timer.assert_called_once()
                self.assertEqual(
                    timer.call_args.args[0], IMAGE_DRAG_RETENTION_MS
                )
                timer.call_args.args[1]()
                self.assertFalse(filename.exists())
        finally:
            listing.deleteLater()
            owner.deleteLater()


if __name__ == "__main__":
    unittest.main()
