"""Single running Qt instance with a local-only command socket."""
from __future__ import annotations

import os
from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "clipmint-single-instance-" + str(os.getuid())
VALID_COMMANDS = {"toggle", "show", "quit", "screenshot-area"}


def send_command(command: str, timeout_ms: int = 350) -> bool:
    if command not in VALID_COMMANDS:
        raise ValueError("Unknown local ClipMint command")
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(timeout_ms):
        socket.abort()
        return False
    socket.write((command + "\n").encode("ascii"))
    ok = socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return bool(ok)


class InstanceServer(QObject):
    def __init__(self, handler, parent=None):
        super().__init__(parent)
        self.handler = handler
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._handle)
        # Calling this in a separate user account cannot contact this uid's
        # socket. Only remove stale sockets when no listener answers.
        if not self.server.listen(SERVER_NAME):
            if send_command("show"):
                raise RuntimeError("ClipMint is already running")
            QLocalServer.removeServer(SERVER_NAME)
            if not self.server.listen(SERVER_NAME):
                raise RuntimeError("Could not start local command socket")

    def _handle(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            if sock is None:
                continue
            if not sock.bytesAvailable():
                sock.waitForReadyRead(250)
            raw = bytes(sock.readAll())[:64]
            cmd = raw.decode("ascii", "ignore").strip()
            sock.disconnectFromServer()
            sock.deleteLater()
            if cmd in VALID_COMMANDS:
                self.handler(cmd)
