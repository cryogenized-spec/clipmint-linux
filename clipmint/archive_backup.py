"""Atomic, owner-only SQLite archive backups for the active ClipMint store.

Uses SQLite's online backup API so in-flight WAL data is captured consistently.
Encrypted history stays encrypted: this NEVER decrypts, exports or rewraps
secrets, and the desktop keyring key is not part of a .sqlite3 backup.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile


class ArchiveBackupError(RuntimeError):
    pass


def backup_archive(
    active_connection: sqlite3.Connection,
    destination: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Create one consistent .sqlite3 backup without modifying the source.

    Normal case is no-overwrite: hard-link a finished, private temporary file
    into place, which fails atomically if the destination appeared meanwhile.
    Explicit overwrite uses an atomic replace in the same directory.

    Does not back up the separate Vault or keyring; encrypted backups require
    access to the original encryption key for future reading.
    """
    target = Path(destination).expanduser()
    if not target.name or target.suffix.lower() != ".sqlite3":
        raise ArchiveBackupError("Choose a .sqlite3 archive backup filename")
    if not target.parent.is_dir():
        raise ArchiveBackupError("The selected destination folder does not exist")
    if target.is_symlink():
        raise ArchiveBackupError("Refusing to overwrite a symbolic link")
    if target.exists() and not overwrite:
        raise FileExistsError("A file with that name already exists")
    if target.exists() and not target.is_file():
        raise ArchiveBackupError("The destination is not a regular file")

    # Never let the user accidentally overwrite their live archive.
    source_files = [
        Path(filename).resolve()
        for _, name, filename in active_connection.execute("PRAGMA database_list")
        if name == "main" and filename
    ]
    if source_files and target.resolve() in source_files:
        raise ArchiveBackupError("Cannot write a backup over ClipMint's live database")

    descriptor, staged_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".building", dir=str(target.parent)
    )
    staged = Path(staged_name)
    backup_connection = None
    try:
        os.fchmod(descriptor, 0o600)
        os.close(descriptor)
        descriptor = -1
        backup_connection = sqlite3.connect(staged)
        active_connection.backup(backup_connection, pages=128, sleep=0.05)
        result = backup_connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise ArchiveBackupError("Backup integrity verification did not pass")
        backup_connection.close()
        backup_connection = None

        os.chmod(staged, 0o600)
        if overwrite:
            # Explicit overwrite accepted by the user in the UI.
            if target.is_symlink():
                raise ArchiveBackupError("Destination became a symbolic link")
            os.replace(staged, target)
        else:
            # Atomic create: never replace an existing file during a race.
            os.link(staged, target)
            staged.unlink()
        return target
    except (sqlite3.Error, OSError) as exc:
        raise ArchiveBackupError(
            "Could not create a verified local archive backup"
        ) from exc
    finally:
        if backup_connection is not None:
            backup_connection.close()
        if descriptor >= 0:
            os.close(descriptor)
        staged.unlink(missing_ok=True)
        # SQLite might have created temporary sidecars; never leave them.
        for suffix in ("-wal", "-shm", "-journal"):
            Path(str(staged) + suffix).unlink(missing_ok=True)
