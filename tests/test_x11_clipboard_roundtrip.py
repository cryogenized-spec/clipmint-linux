"""Real cross-process X11 clipboard round-trip on an isolated Xvfb display.

The test uses synthetic text only. It is intentionally not a substitute for
physical Linux Mint/Cinnamon/Nemo acceptance.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from time import monotonic
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from clipmint.clipboard_formats import from_mime, mime_from_entry
from clipmint.store import ClipStore


@unittest.skipUnless(
    os.environ.get("DISPLAY") and shutil.which("xclip"),
    "Needs an isolated X11 display and xclip",
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

    def test_xdotool_can_access_virtual_x11(self):
        if not shutil.which("xdotool"):
            self.skipTest("xdotool absent")
        subprocess.run(
            ["xdotool", "mousemove", "25", "25"],
            check=True, capture_output=True, timeout=8,
        )


if __name__ == "__main__":
    unittest.main()
