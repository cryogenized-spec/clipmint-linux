"""Real cross-process X11 clipboard round-trip on an isolated Xvfb display.

The test uses synthetic text only. It is intentionally not a substitute for
physical Linux Mint/Cinnamon/Nemo acceptance.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from unittest.mock import patch
from time import monotonic
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from clipmint.clipboard_formats import from_mime, mime_from_entry
from clipmint.store import ClipStore


@unittest.skipUnless(
    os.environ.get("CLIPMINT_X11_TEST") == "1"
    and os.environ.get("QT_QPA_PLATFORM") == "xcb"
    and os.environ.get("DISPLAY") and shutil.which("xclip"),
    "Explicit isolated X11 test opt-in, xcb backend and xclip required",
)
class X11ClipboardRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_copy_into_history_and_republish_from_history(self):
        copied = b"ClipMint Xvfb clipboard fixture 8765"
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "text/plain", "-in"],
            input=copied, check=True, timeout=8,
        )
        QTest.qWait(160)
        current = QApplication.clipboard().mimeData()
        entry = from_mime(current)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.kind, "text")
        self.assertEqual(entry.content, copied)

        with TemporaryDirectory() as root:
            store = ClipStore(Path(root) / "history.sqlite3")
            try:
                ident = store.add(
                    entry.kind, entry.content, entry.preview,
                    formats=entry.formats,
                )
                self.assertIsNotNone(ident)
                kind, original = store.get(ident)
                QApplication.clipboard().setMimeData(
                    mime_from_entry(kind, original, store.get_formats(ident))
                )
                QTest.qWait(160)
                # Qt is the clipboard *owner* here: it must process X11
                # selection requests while xclip reads in another process.
                reply = subprocess.Popen(
                    ["xclip", "-selection", "clipboard", "-o"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                deadline = monotonic() + 8
                while reply.poll() is None and monotonic() < deadline:
                    QTest.qWait(20)
                if reply.poll() is None:
                    reply.kill()
                    reply.communicate()
                    self.fail("X11 clipboard readback timed out")
                stdout, stderr = reply.communicate(timeout=2)
                self.assertEqual(reply.returncode, 0, stderr)
                self.assertEqual(stdout, copied)
            finally:
                store.close()

    def test_hidden_window_captures_external_text_across_x11(self):
        """The real X11 selection must reach SQLite after the window closes."""
        from clipmint.app import ClipMintWindow

        previous_data = os.environ.get("XDG_DATA_HOME")
        previous_config = os.environ.get("XDG_CONFIG_HOME")
        window = None
        with TemporaryDirectory() as root:
            os.environ["XDG_DATA_HOME"] = root
            os.environ["XDG_CONFIG_HOME"] = str(Path(root) / "config")
            try:
                self.app.setQuitOnLastWindowClosed(False)
                with patch("clipmint.app.blocked_foreground", return_value=False):
                    window = ClipMintWindow()
                    if window.tray is not None:
                        window.tray.hide()
                        window.tray = None
                    window.autosort_enabled = False
                    window.show()
                    self.app.processEvents()
                    window.close()
                    self.app.processEvents()
                    self.assertFalse(window.isVisible())
                    self.assertFalse(window.store.closed)

                    sample = b"ClipMint X11 hidden window history sample"
                    subprocess.run(
                        ["xclip", "-selection", "clipboard",
                         "-t", "text/plain", "-in"],
                        input=sample, check=True, timeout=8,
                    )
                    QTest.qWait(450)
                    matches = window.store.search(
                        "ClipMint X11 hidden window history sample", "Work"
                    )
                    self.assertTrue(matches, "Hidden X11 watcher missed external copy")
                    self.assertEqual(window.store.get(matches[0].id),
                                     ("text", sample))
            finally:
                if window is not None:
                    window._closing = True
                    if not window.store.closed:
                        window.store.close()
                    window.close()
                    window.deleteLater()
                if previous_data is None:
                    os.environ.pop("XDG_DATA_HOME", None)
                else:
                    os.environ["XDG_DATA_HOME"] = previous_data
                if previous_config is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = previous_config

    def test_xdotool_can_access_virtual_x11(self):
        if not shutil.which("xdotool"):
            self.skipTest("xdotool absent")
        subprocess.run(
            ["xdotool", "mousemove", "25", "25"],
            check=True, capture_output=True, timeout=8,
        )


if __name__ == "__main__":
    unittest.main()
