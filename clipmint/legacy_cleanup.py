"""Explicit, verified deletion of the legacy plaintext SQLite history.

This cannot guarantee forensic erasure on SSDs, snapshots, backups or other
copies. Never run as part of automatic encrypted-history migration.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import hmac
import os
import stat

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
        "SELECT id,kind,content,formats,preview,pinned,bin,favorite,"
        "created_at,touch_seq FROM clips ORDER BY id"
    ):
        (ident, kind, raw, packed, preview, pinned, folder, favorite,
         created_at, touch_seq) = row
        sealed = encrypted.conn.execute(
            "SELECT content,pinned,bin,favorite,kind,created_at,touch_seq "
            "FROM clips WHERE id=?",
            (ident,),
        ).fetchone()
        # Older migrations normalize zero touch sequence values to the ID.
        expected_touch = touch_seq if touch_seq else ident
        if sealed is None or (sealed[1], sealed[2], sealed[3], sealed[4],
                              sealed[5], sealed[6]) != (
                pinned, folder, favorite, kind, created_at, expected_touch):
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

    original_bins = {
        name for (name,) in legacy.execute("SELECT name FROM bins")
    }
    encrypted_bins = {
        name for (name,) in encrypted.conn.execute("SELECT name FROM bins")
    }
    if not original_bins.issubset(encrypted_bins):
        raise HistorySecurityError("Encrypted history is missing legacy bins")

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


def _require_no_other_open_handles(old: Path) -> None:
    """Reject legacy-file users not visible to SQLite's WAL shared locks.

    An SQLite connection that opened the database but has not yet executed
    a statement does not hold a SHARED lock. Linux /proc exposes its still
    open file descriptor. Be conservative: no deletion unless this process's
    one cleanup connection is the sole visible holder of the legacy inode.
    A missing/restricted process table is a reason to refuse cleanup.
    """
    if os.name != "posix" or not Path("/proc/self/fd").is_dir():
        raise HistorySecurityError("Cannot inspect open SQLite connections")
    info = old.stat(follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise HistorySecurityError(
            "Legacy database must be a private owner-only regular file"
        )
    identity = (info.st_dev, info.st_ino)
    own = os.getpid()
    own_handles = 0
    try:
        with os.scandir("/proc") as processes:
            for proc in processes:
                if not proc.name.isdigit():
                    continue
                try:
                    details = proc.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue
                # A 0600 database inside a 0700 app directory is private
                # to the current owner (plus trusted root). Do not fail
                # because unrelated users' process FDs are inaccessible.
                if details.st_uid != os.getuid():
                    continue
                try:
                    with os.scandir(f"/proc/{proc.name}/fd") as fds:
                        for fd in fds:
                            try:
                                opened = fd.stat(follow_symlinks=True)
                            except FileNotFoundError:
                                continue
                            except PermissionError as exc:
                                # Linux can deny inspecting unrelated (often
                                # sandboxed/non-dumpable) same-UID processes'
                                # terminal/socket FDs. Never ignore denial
                                # for our own process or a ClipMint process;
                                # the SQLite VFS lock still guards other
                                # active database users.
                                if int(proc.name) == own:
                                    raise HistorySecurityError(
                                        "Cannot inspect own open file handles"
                                    ) from exc
                                try:
                                    command = Path(
                                        f"/proc/{proc.name}/cmdline"
                                    ).read_bytes()[:8192].lower()
                                except OSError as problem:
                                    raise HistorySecurityError(
                                        "Cannot identify process with unreadable FDs"
                                    ) from problem
                                if b"clipmint" in command:
                                    raise HistorySecurityError(
                                        "Cannot inspect another ClipMint process"
                                    ) from exc
                                continue
                            if (opened.st_dev, opened.st_ino) != identity:
                                continue
                            if int(proc.name) != own:
                                raise HistorySecurityError(
                                    "Another process still has legacy history open"
                                )
                            own_handles += 1
                except FileNotFoundError:
                    continue
    except OSError as exc:
        raise HistorySecurityError(
            "Could not inspect all running app processes; refusing cleanup"
        ) from exc
    if own_handles != 1:
        raise HistorySecurityError(
            "Another legacy history handle is still open; close old app instances"
        )


def remove_verified_legacy_history(encrypted: EncryptedClipStore) -> int:
    """Only remove a verified WAL archive with *no other SQLite connection*.

    SQLite's WAL BEGIN EXCLUSIVE alone holds a writer lock, so idle readers
    can survive and later write to unlinked files. Setting locking_mode to
    EXCLUSIVE *before the first database access* acquires a true exclusive
    VFS lock and fails closed when even an idle connection is attached.
    Keep that lock until the unlink is complete.
    """
    old = _legacy_path(encrypted)
    _check_persisted_key(encrypted)
    try:
        with closing(_connect_legacy(old, "rw")) as legacy:
            # IMPORTANT: WAL BEGIN EXCLUSIVE by itself is equivalent to a
            # writer lock and DOES NOT exclude idle open readers. All normal
            # WAL clients hold SQLITE_LOCK_SHARED even outside a transaction.
            # A true exclusive VFS lock rejects any such existing connection.
            if legacy.execute("PRAGMA main.locking_mode=EXCLUSIVE").fetchone() != ("exclusive",):
                raise HistorySecurityError("Cannot obtain exclusive SQLite access")
            legacy.execute("BEGIN EXCLUSIVE")
            try:
                if legacy.execute("PRAGMA main.journal_mode").fetchone() != ("wal",):
                    raise HistorySecurityError(
                        "Unexpected legacy journal mode; refusing removal"
                    )
                count = _verify_rows(encrypted, legacy)
                _check_persisted_key(encrypted)
            finally:
                legacy.execute("ROLLBACK")

            # A crash or filesystem failure between multiple unlinks must
            # never strand a legacy DB without its only committed WAL rows.
            # The VFS exclusive lock persists across transactions when
            # locking_mode=EXCLUSIVE; checkpoint all content into the main DB
            # and abort if SQLite cannot finish the checkpoint.
            checkpoint = legacy.execute(
                "PRAGMA main.wal_checkpoint(TRUNCATE)"
            ).fetchone()
            if checkpoint is None or checkpoint[0] != 0:
                raise HistorySecurityError(
                    "Legacy WAL could not be fully checkpointed"
                )

            legacy.execute("BEGIN EXCLUSIVE")
            try:
                count = _verify_rows(encrypted, legacy)
                _check_persisted_key(encrypted)
                _require_no_other_open_handles(old)
                for suffix in ("", "-wal", "-shm"):
                    if Path(str(old) + suffix).is_symlink():
                        raise HistorySecurityError(
                            "Refusing to remove a symlinked legacy file"
                        )
                # Rechecked under the exclusive lock and a Linux open-file
                # scan, including SQLite connections with no active query.
                # If a later unlink fails, fully checkpointed main DB rows
                # remain recoverable without the WAL sidecar.
                for suffix in ("-wal", "-shm", ""):
                    Path(str(old) + suffix).unlink(missing_ok=True)
            finally:
                legacy.execute("ROLLBACK")
    except (sqlite3.Error, UnicodeError) as exc:
        raise HistorySecurityError(
            "Could not exclusively verify old plaintext history; nothing removed"
        ) from exc
    return count
