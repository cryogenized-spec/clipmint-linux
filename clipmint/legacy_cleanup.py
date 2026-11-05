"""Explicit, verified deletion of the legacy plaintext SQLite history.

This cannot guarantee forensic erasure on SSDs, snapshots, backups or other
copies. Never run as part of automatic encrypted-history migration.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import hmac

from .clipboard_formats import bundle_from_bytes
from .secure_history import (
    EncryptedClipStore, HistorySecurityError, key_from_secret_service
)


def _legacy_path(encrypted: EncryptedClipStore) -> Path:
    if not isinstance(encrypted, EncryptedClipStore) or encrypted.closed:
        raise HistorySecurityError("Unlock encrypted history before removing old history")
    if encrypted.path.name != "secure-history.sqlite3":
        raise HistorySecurityError("Unexpected encrypted history database path")
    old = encrypted.path.with_name("history.sqlite3")
    if old.is_symlink() or not old.is_file() or old.resolve() == encrypted.path.resolve():
        raise HistorySecurityError("Expected legacy plaintext history file was not found")
    for suffix in ("-wal", "-shm"):
        if Path(str(old) + suffix).is_symlink():
            raise HistorySecurityError("Legacy sidecar symlink is not safe to remove")
    return old


def _check_persisted_key(encrypted: EncryptedClipStore) -> None:
    # A cached in-memory key is not a viable recovery key after app restart.
    # Never create a replacement key merely to authorize legacy deletion.
    available = key_from_secret_service(create=False)
    if not hmac.compare_digest(available, encrypted._dedup_key):
        raise HistorySecurityError(
            "Desktop keyring key changed; refusing removal of the recovery copy"
        )


def _verify_rows(encrypted: EncryptedClipStore, legacy: sqlite3.Connection) -> int:
    if encrypted.conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
        raise HistorySecurityError("Encrypted history integrity check failed")
    if legacy.execute("PRAGMA quick_check").fetchone() != ("ok",):
        raise HistorySecurityError("Legacy history integrity check failed")
    count = 0
    for row in legacy.execute(
        "SELECT id,kind,content,formats,preview,pinned,bin,favorite "
        "FROM clips ORDER BY id"
    ):
        ident, kind, raw, packed, preview, pinned, folder, favorite = row
        sealed = encrypted.conn.execute(
            "SELECT content,pinned,bin,favorite,kind FROM clips WHERE id=?",
            (ident,),
        ).fetchone()
        if sealed is None or (sealed[1], sealed[2], sealed[3], sealed[4]) != (
                pinned, folder, favorite, kind):
            raise HistorySecurityError(
                "Encrypted history does not match legacy row metadata"
            )
        opened, opened_preview, opened_formats = encrypted._open(bytes(sealed[0]))
        old_formats = bundle_from_bytes(bytes(packed) if packed else None)
        if (opened != bytes(raw) or opened_preview != preview
                or opened_formats != old_formats):
            raise HistorySecurityError(
                "Encrypted history does not match legacy clip content"
            )
        count += 1

    tags = legacy.execute(
        "SELECT clip_id,tag FROM clip_tags ORDER BY clip_id,tag"
    ).fetchall()
    current_tags = set(encrypted.conn.execute(
        "SELECT clip_id,tag FROM clip_tags"
    ).fetchall())
    if any(item not in current_tags for item in tags):
        raise HistorySecurityError("Encrypted history is missing legacy clip tags")

    legacy_templates = legacy.execute(
        "SELECT name,body FROM templates ORDER BY name"
    ).fetchall()
    current_templates = {
        name: body for _ident, name, body in encrypted.templates()
    }
    for name, body in legacy_templates:
        if current_templates.get(name) != bytes(body).decode("utf-8"):
            raise HistorySecurityError(
                "Encrypted history does not contain a legacy template"
            )
    return count


def _connect_legacy(path: Path, mode: str) -> sqlite3.Connection:
    # Exact mode avoids accidentally creating a missing/different database.
    from urllib.parse import quote
    uri = "file:" + quote(str(path), safe="/") + "?mode=" + mode
    return sqlite3.connect(uri, uri=True, timeout=0.3, isolation_level=None)


def verify_legacy_history(encrypted: EncryptedClipStore) -> tuple[Path, int]:
    """Non-destructively verify original contents before the user is prompted."""
    old = _legacy_path(encrypted)
    _check_persisted_key(encrypted)
    try:
        with closing(_connect_legacy(old, "ro")) as legacy:
            # Preliminary verification is informational. The final check
            # must be repeated while exclusive writer access is held.
            legacy.execute("BEGIN")
            try:
                count = _verify_rows(encrypted, legacy)
            finally:
                legacy.execute("ROLLBACK")
    except (sqlite3.Error, UnicodeError) as exc:
        raise HistorySecurityError("Could not verify old plaintext history") from exc
    return old, count


def remove_verified_legacy_history(encrypted: EncryptedClipStore) -> int:
    """Verify and unlink original SQLite files while excluding all writers.

    BEGIN EXCLUSIVE retains the WAL writer lock from the final verification
    until after unlink. SQLite does not rely on advisory fcntl/flock locks.
    """
    old = _legacy_path(encrypted)
    _check_persisted_key(encrypted)
    try:
        with closing(_connect_legacy(old, "rw")) as legacy:
            # Other readers are acceptable, but no writer may race the scan.
            # Under WAL, BEGIN EXCLUSIVE obtains the same writer lock as
            # BEGIN IMMEDIATE. Fail closed if it is held elsewhere.
            legacy.execute("BEGIN EXCLUSIVE")
            try:
                count = _verify_rows(encrypted, legacy)
                _check_persisted_key(encrypted)
                for suffix in ("", "-wal", "-shm"):
                    if Path(str(old) + suffix).is_symlink():
                        raise HistorySecurityError(
                            "Refusing to remove a symlinked legacy file"
                        )
                # Keep the writer lock *throughout* all unlinks. On POSIX
                # unlinking the open inode is safe; no unlocked read/erase gap.
                for suffix in ("-wal", "-shm", ""):
                    Path(str(old) + suffix).unlink(missing_ok=True)
            finally:
                legacy.execute("ROLLBACK")
    except (sqlite3.Error, UnicodeError) as exc:
        raise HistorySecurityError(
            "Could not exclusively verify old plaintext history; nothing removed"
        ) from exc
    return count
