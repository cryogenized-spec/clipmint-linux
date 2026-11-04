"""Single-instance local IPC and keyboard popup smoke tests."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_SESSION_TYPE", "x11")
from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QLocalServer
from PySide6.QtCore import Qt, QSettings
from PySide6.QtTest import QTest
from tempfile import TemporaryDirectory
from pathlib import Path

from clipmint import single_instance
from clipmint.quick_popup import QuickPopup
from clipmint.store import ClipStore


class PopUpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_keyboard_navigation_and_fuzzy_filter(self):
        with TemporaryDirectory() as root:
            db = ClipStore(Path(root) / "history.sqlite3")
            try:
                ident = db.add("text", b"Invoice Number 22", "Invoice Number 22")
                db.add("text", b"Other text", "Other text")
                picked = []
                popup = QuickPopup(db, lambda *args: picked.append(args))
                popup.target_window = None
                popup.search.setText("invoce")
                self.app.processEvents()
                self.assertGreaterEqual(popup.items.count(), 1)
                popup.show()
                popup.search.setFocus()
                QTest.keyClick(popup.search, Qt.Key.Key_Return)
                self.assertEqual(picked[0][0], ident)
                self.assertFalse(picked[0][1])
                popup.close()
            finally:
                db.close()

    def test_single_instance_command_handshake(self):
        unique = "clipmint-unit-test-" + str(os.getpid())
        messages = []
        with TemporaryDirectory() as runtime, patch.dict(
            os.environ, {"XDG_RUNTIME_DIR": runtime}
        ), patch.object(single_instance, "SERVER_NAME", unique):
            server = single_instance.InstanceServer(messages.append)
            try:
                self.assertTrue(
                    server.server.socketOptions() &
                    QLocalServer.SocketOption.UserAccessOption
                )
                socket_path = Path(server.server.fullServerName())
                if socket_path.is_socket():
                    self.assertEqual(socket_path.stat().st_mode & 0o077, 0)
                private = Path(runtime) / "clipmint"
                self.assertEqual(private.stat().st_mode & 0o077, 0)
                self.assertEqual((private / "instance.lock").stat().st_mode & 0o077, 0)
                for command in ("toggle", "screenshot-area", "record-area", "ping"):
                    self.assertTrue(single_instance.send_command(command))
                    for _ in range(20):
                        self.app.processEvents()
                        if messages and messages[-1] == command:
                            break
                self.assertEqual(
                    messages, ["toggle", "screenshot-area", "record-area", "ping"]
                )
                # Even when the event loop is busy, a second watcher cannot
                # take over the filesystem socket or create a second server.
                with patch.object(single_instance, "send_command", return_value=False):
                    with self.assertRaisesRegex(RuntimeError, "already running"):
                        single_instance.InstanceServer(
                            messages.append, occupied_command="ping"
                        )
                self.assertTrue(server.server.isListening())
            finally:
                server.close()
                QLocalServer.removeServer(unique)

            # The OS releases the advisory lock for a clean app restart.
            replacement = single_instance.InstanceServer(messages.append)
            try:
                self.assertTrue(replacement.server.isListening())
            finally:
                replacement.close()
                QLocalServer.removeServer(unique)


if __name__ == "__main__":
    unittest.main()
