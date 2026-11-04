"""Single running Qt instance with a local-only command socket."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import stat
from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "clipmint-single-instance-" + str(os.getuid())
VALID_COMMANDS = {"toggle", "show", "quit", "ping", "screenshot-area", "record-area"}


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


def _acquire_instance_lock() -> int:
    """Hold an owner-only advisory lock for the life of the Qt IPC server.

    File locks survive application stalls and release automatically on crashes.
    The private directory is specific to the local account and not the socket
    pathname, so a slow existing server cannot be replaced by a new watcher.
    """
    configured = os.environ.get("XDG_RUNTIME_DIR", "")
    base = Path(configured) if configured and Path(configured).is_absolute() else (
        Path.home() / ".cache"
    )
    private = base / "clipmint"
    if private.is_symlink():
        raise RuntimeError("ClipMint runtime directory must not be a symlink")
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = private.stat()
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid():
        raise RuntimeError("ClipMint runtime directory is not owned by this user")
    os.chmod(private, 0o700)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    fd = os.open(private / "instance.lock", flags, 0o600)
    try:
        current = os.fstat(fd)
        if not stat.S_ISREG(current.st_mode) or current.st_uid != os.getuid():
            raise RuntimeError("ClipMint instance lock must be a user-owned file")
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("ClipMint is already running") from exc
        return fd
    except BaseException:
        os.close(fd)
        raise


class InstanceServer(QObject):
    def __init__(self, handler, parent=None, occupied_command="show"):
        super().__init__(parent)
        self.handler = handler
        self.server = QLocalServer(self)
        self._lock_fd = _acquire_instance_lock()
        try:
            # Restrict IPC commands such as "quit" to the logged-in user.
            # Qt requires socket options to be applied before listen().
            self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
            self.server.newConnection.connect(self._handle)
            if not self.server.listen(SERVER_NAME):
                # Only the lock owner may clean up its own stale socket.
                if send_command(occupied_command):
                    raise RuntimeError("ClipMint is already running")
                # Also detect a pre-upgrade instance which did not yet hold
                # this file lock, but is still accepting IPC connections.
                probe = QLocalSocket()
                probe.connectToServer(SERVER_NAME)
                occupied = probe.waitForConnected(350)
                probe.abort()
                if occupied:
                    raise RuntimeError("ClipMint is already running")
                QLocalServer.removeServer(SERVER_NAME)
                if not self.server.listen(SERVER_NAME):
                    raise RuntimeError("Could not start local command socket")
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        """Release the IPC server and its advisory lock (also on normal exit)."""
        self.server.close()
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

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
