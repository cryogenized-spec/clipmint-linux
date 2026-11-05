"""Explicit, verified deletion of the legacy plaintext SQLite history.

This cannot guarantee forensic erasure on SSDs, snapshots, backups or other
copies. Never run as part of automatic encrypted-history migration.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3

from .clipboard_formats import bundle_from_bytes
from .secure_history import EncryptedClipStore, HistorySecurityError


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


def verify_legacy_history(encrypted: EncryptedClipStore) -> tuple[Path, int]:
    """Return (legacy path, checked clip count) after full authenticated read-back.

    Reject any missing/mismatched clip, format, preview, pin, bin, tag or
    template. A later edit/deletion can invalidate the match; in that case
    keep the plaintext original for manual review.
    """
    old = _legacy_path(encrypted)
    if encrypted.conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
        raise HistorySecurityError("Encrypted history integrity check failed")

    # mode=ro avoids creating an unrelated database and avoids modifying
    # the legacy file during verification.
    from urllib.parse import quote
    uri = "file:" + quote(str(old), safe="/") + "?mode=ro"
    count = 0
    try:
        with sqlite3.connect(uri, uri=True, timeout=1) as legacy:
            if legacy.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise HistorySecurityError("Legacy history integrity check failed")
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
            current_tags = encrypted.conn.execute(
                "SELECT clip_id,tag FROM clip_tags ORDER BY clip_id,tag"
            ).fetchall()
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
    except (sqlite3.Error, UnicodeError) as exc:
        raise HistorySecurityError("Could not verify old plaintext history") from exc
    return old, count


def remove_verified_legacy_history(encrypted: EncryptedClipStore) -> int:
    """Re-verify then unlink only known legacy SQLite files on explicit call."""
    old, count = verify_legacy_history(encrypted)
    # Close read-only connection before unlinking. Parent and old path have
    # been checked; refuse symlink sidecars again to avoid unsafe traversal.
    for suffix in ("", "-wal", "-shm"):
        target = Path(str(old) + suffix)
        if target.is_symlink():
            raise HistorySecurityError("Refusing to remove a symlinked legacy file")
    for suffix in ("-wal", "-shm", ""):
        Path(str(old) + suffix).unlink(missing_ok=True)
    return count
