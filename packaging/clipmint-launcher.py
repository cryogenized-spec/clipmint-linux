#!/usr/bin/python3
"""Fast, stdlib-only entry point for the installed ClipMint application.

A Cinnamon shortcut must not start the large frozen Qt application merely
to send a command to the already-running clipboard watcher. This entry point
uses the owner's existing Qt local socket, then execs the full application
only when no running instance can accept the command.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import stat
import sys
import tempfile


def requested_action(argv: list[str]) -> str | None:
    if "--screenshot-area" in argv:
        return "screenshot-area"
    if "--record-area" in argv:
        return "record-area"
    if "--toggle" in argv:
        return "toggle"
    if "--quit" in argv:
        return "quit"
    if "--hidden" in argv:
        return "ping"
    return "show" if not argv else None


def signal_existing(command: str) -> bool:
    # QLocalServer's non-absolute name maps to Qt's temporary directory on X11.
    # Never contact a socket owned by another user or with public permissions.
    path = Path(tempfile.gettempdir()) / f"clipmint-single-instance-{os.getuid()}"
    try:
        info = path.lstat()
        if (not stat.S_ISSOCK(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            return False
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(0.15)
            client.connect(str(path))
            client.sendall((command + "\n").encode("ascii"))
        return True
    except OSError:
        return False


def main(argv: list[str]) -> None:
    command = requested_action(argv)
    if command is not None and signal_existing(command):
        return
    if command == "quit":
        # A stopped application has nothing to quit.
        return
    binary = Path(__file__).resolve().with_name("ClipMintApp")
    os.execv(str(binary), [str(binary), *argv])


if __name__ == "__main__":
    main(sys.argv[1:])
