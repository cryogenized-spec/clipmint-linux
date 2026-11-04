"""Atomic, private SQLite online backups of ClipMint's active history store.

Uses sqlite3.Connection.backup(), never decrypts history and never exports
keyring credentials. Rejects unsafe staging directories and destination WAL
sidecars. The source database is never modified by this operation.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import time


class ArchiveBackupError(RuntimeError):
    pass


def _has_sidecars(target: Path) -> bool:
    return any(
        Path(str(target) + suffix).exists()
        for suffix in ("-wal", "-shm", "-journal")
    )


def _verify_safe_destination_directory(parent: Path) -> None:
    """Reject any writable ancestor controlled by an untrusted UID.

    A sticky directory owned by another UID can still be renamed by its
    *owner*. It is not safe to stage sensitive clipboard content there even
    when our staging directory itself is 0700. Resolve before use and refuse
    writable ancestors which other users can replace.
    """
    owner = os.geteuid()
    for ancestor in (parent, *parent.parents):
        details = ancestor.stat()
        mode = details.st_mode
        shared_writes = mode & (stat.S_IWGRP | stat.S_IWOTH)
        if not shared_writes:
            continue
        if not (mode & stat.S_ISVTX) or details.st_uid != owner:
            raise ArchiveBackupError(
                "Choose a private backup folder in your home directory. "
                "This destination or an ancestor can be replaced by "
                "another account."
            )


def backup_archive(
    active_connection: sqlite3.Connection,
    destination: Path,
    *,
    overwrite: bool = False,
    timeout_seconds: float = 8.0,
) -> Path:
    """Export a consistent SQLite snapshot to an owner-only file.

    No-overwrite publishing uses an atomic hard-link; an explicit overwrite
    uses an atomic replace only when no active destination sidecars exist.
    The SQLite staging database lives inside a private 0700 directory.
    """
    target = Path(destination).expanduser()
    if not target.name or target.suffix.lower() != ".sqlite3":
        raise ArchiveBackupError("Choose a .sqlite3 archive backup filename")
    if not target.parent.is_dir():
        raise ArchiveBackupError("The selected destination folder does not exist")

    parent = target.parent.resolve(strict=True)
    _verify_safe_destination_directory(parent)
    # Work with canonical directory components after safety validation.
    # Otherwise a symlinked parent could be swapped before publication.
    target = parent / target.name
    if active_connection.in_transaction:
        raise ArchiveBackupError(
            "An unfinished database write is blocking the backup. "
            "Finish or cancel the pending operation, or restart ClipMint."
        )
    if target.is_symlink():
        raise ArchiveBackupError("Refusing to overwrite a symbolic link")
    if target.exists() and not overwrite:
        raise FileExistsError("A backup with that filename already exists")
    if target.exists() and not target.is_file():
        raise ArchiveBackupError("The destination is not a regular file")
    if overwrite and _has_sidecars(target):
        raise ArchiveBackupError(
            "This existing SQLite file has active WAL/journal sidecars. "
            "Close the program using it or choose another filename."
        )

    source_files = [
        Path(filename).resolve()
        for _, name, filename in active_connection.execute(
            "PRAGMA database_list"
        )
        if name == "main" and filename
    ]
    if source_files and target.resolve() in source_files:
        raise ArchiveBackupError(
            "Cannot write a backup over ClipMint's live database"
        )

    stage_dir = Path(tempfile.mkdtemp(
        prefix=".clipmint-backup-", dir=str(parent)
    ))
    staged = stage_dir / "snapshot.sqlite3"
    writer = None
    try:
        os.chmod(stage_dir, 0o700)
        writer = sqlite3.connect(staged, timeout=2.0)
        os.chmod(staged, 0o600)
        start = time.monotonic()

        def progress(_status: int, _remaining: int, _total: int) -> None:
            if time.monotonic() - start >= timeout_seconds:
                raise ArchiveBackupError(
                    "Archive backup took too long. Close other SQLite users "
                    "or applications and try again."
                )

        active_connection.backup(
            writer, pages=128, progress=progress, sleep=0.05
        )
        result = writer.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise ArchiveBackupError("Backup integrity verification did not pass")
        writer.close()
        writer = None
        if target.is_symlink():
            raise ArchiveBackupError("The destination became a symbolic link")
        if overwrite:
            if _has_sidecars(target):
                raise ArchiveBackupError(
                    "Destination SQLite sidecars appeared during backup; "
                    "the original file was not replaced."
                )
            os.replace(staged, target)
        else:
            # Fails atomically if a destination appears while we are building.
            os.link(staged, target)
        return target
    except (sqlite3.Error, OSError) as exc:
        raise ArchiveBackupError(
            "Could not create a verified local archive backup"
        ) from exc
    finally:
        if writer is not None:
            writer.close()
        shutil.rmtree(stage_dir)
