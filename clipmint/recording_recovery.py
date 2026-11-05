"""Conservative recovery of unfinished screen recordings after a crash.

Nothing is removed or renamed on startup without an explicit user choice.
Do not claim unfinished MP4 files are playable (the final trailer may be absent).
"""
from __future__ import annotations

from pathlib import Path
import re
import os
import time

from .capture import recordings_dir

_PENDING = re.compile(r"^\.pending-recording-\d{8}-\d{6}-\d{6}\.(?:mp4|gif)$")


def _writer_may_be_active(path: Path) -> bool:
    """Conservatively detect a surviving FFmpeg writer on Linux.

    A fresh file is never treated as abandoned. Our FFmpeg command includes
    the absolute output path, so inspect same-user /proc cmdlines as a
    best-effort safeguard against orphaned FFmpeg processes.
    """
    try:
        if time.time() - path.stat().st_mtime < 10:
            return True
        proc = Path("/proc")
        if not proc.is_dir():
            return True  # Fail closed if process inspection is unavailable.
        target = os.fsencode(str(path.resolve()))
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                if entry.stat().st_uid != os.getuid():
                    continue
                command = (entry / "cmdline").read_bytes()
            except (OSError, PermissionError):
                # A same-user process we cannot inspect is ambiguous.
                # Do not perform a destructive operation on uncertainty.
                return True
            if b"ffmpeg" in command.lower() and target in command:
                return True
    except (OSError, PermissionError):
        return True
    return False


def pending_recordings(folder: Path | None = None) -> list[Path]:
    folder = Path(folder) if folder is not None else recordings_dir()
    if not folder.is_dir():
        return []
    result = []
    for entry in folder.iterdir():
        # Never follow a symlink to a file outside ClipMint's recording folder.
        if (not _PENDING.fullmatch(entry.name) or entry.is_symlink()
                or not entry.is_file() or _writer_may_be_active(entry)):
            continue
        result.append(entry)
    return sorted(result, key=lambda path: path.name)


def resolve_pending(path: Path, action: str) -> Path | None:
    """Recover or discard one explicitly selected file; preserve on failure."""
    path = Path(path)
    if (not _PENDING.fullmatch(path.name) or path.is_symlink()
            or not path.is_file()):
        raise ValueError("Not an unfinished ClipMint recording")
    if action not in ("recover", "discard"):
        raise ValueError("Unknown recovery action")
    # Re-check immediately before the operation: the file may have gained
    # an active writer after the startup dialog was shown.
    if _writer_may_be_active(path):
        raise ValueError("Recording may still be in use by FFmpeg")
    log = path.with_suffix(".ffmpeg.log")
    if action == "discard":
        path.unlink()
        if not log.is_symlink():
            log.unlink(missing_ok=True)
        return None
    # The 'recovered' prefix is visible in the Recordings gallery.
    # Reserve a unique name and never overwrite a previously saved file.
    name = path.name.replace(".pending-recording-", "recovered-recording-", 1)
    destination = path.with_name(name)
    index = 1
    while destination.exists():
        destination = path.with_name(f"{Path(name).stem}-{index}{path.suffix}")
        index += 1
    path.rename(destination)
    if log.is_file() and not log.is_symlink():
        log.rename(destination.with_suffix(".ffmpeg.log"))
    return destination
