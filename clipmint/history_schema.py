"""Idempotent SQLite history schema creation and legacy migrations.

This module owns only SQL schema, indexes, user-version compatibility, and
safe legacy MIME table replacement. It does not touch clipboard content,
retention settings, encryption keys or UI state.

The original SAVEPOINT/ROLLBACK migration and metadata indexes are retained.
"""
from __future__ import annotations

import sqlite3

from .clip_model import Clip, DEFAULT_BINS, classify


def initialize_history_schema(conn: sqlite3.Connection) -> None:
    """Bring an opened history connection to the current schema."""
    # Match the public classify() rules inside SQL, so category selection
    # happens before the result limit rather than dropping old matches.
    conn.create_function(
        "clipmint_category", 2,
        lambda kind, preview: classify(Clip(0, kind, preview, False, "")),
        deterministic=True,
    )
    conn.execute("PRAGMA secure_delete=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS clips (
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL CHECK(kind IN ('text', 'image', 'files')),
        content BLOB NOT NULL,
        formats BLOB,
        preview TEXT NOT NULL,
        pinned INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        bin TEXT NOT NULL DEFAULT 'Work'
    )""")
    # Preserve old ClipMint histories. Existing records are assigned to Work.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(clips)")}
    if "formats" not in columns:
        conn.execute("ALTER TABLE clips ADD COLUMN formats BLOB")
    if "bin" not in columns:
        conn.execute("ALTER TABLE clips ADD COLUMN bin TEXT NOT NULL DEFAULT 'Work'")
    conn.execute("""CREATE TABLE IF NOT EXISTS bins (
        name TEXT PRIMARY KEY,
        position INTEGER NOT NULL
    )""")
    for index, name in enumerate(DEFAULT_BINS):
        conn.execute("INSERT OR IGNORE INTO bins(name,position) VALUES(?,?)", (name, index))
    original_schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='clips'"
    ).fetchone()[0]
    if "'files'" not in original_schema:
        # Original v0.3 database CHECK only permitted text/images. Rebuild
        # transactionally, retaining row IDs, timestamps, pins and bins.
        # Any failure rolls the whole migration back rather than dropping
        # or silently rewriting user history.
        conn.execute("SAVEPOINT clipmint_mime_upgrade")
        try:
            conn.execute("""CREATE TABLE clips_mime_upgrade (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL CHECK(kind IN ('text','image','files')),
                content BLOB NOT NULL, formats BLOB, preview TEXT NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT
                  (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                bin TEXT NOT NULL DEFAULT 'Work'
            )""")
            conn.execute("""INSERT INTO clips_mime_upgrade
                (id,kind,content,formats,preview,pinned,created_at,bin)
                SELECT id,kind,content,formats,preview,pinned,created_at,bin
                FROM clips""")
            conn.execute("DROP TABLE clips")
            conn.execute("ALTER TABLE clips_mime_upgrade RENAME TO clips")
            conn.execute("RELEASE SAVEPOINT clipmint_mime_upgrade")
        except Exception:
            conn.execute("ROLLBACK TO SAVEPOINT clipmint_mime_upgrade")
            conn.execute("RELEASE SAVEPOINT clipmint_mime_upgrade")
            raise
    # Non-destructive metadata migration. Favourites and labels are
    # intentionally separate from pinning/retention protection.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(clips)")}
    if "favorite" not in columns:
        conn.execute("ALTER TABLE clips ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0")
    conn.execute("""CREATE TABLE IF NOT EXISTS clip_tags (
        clip_id INTEGER NOT NULL, tag TEXT NOT NULL COLLATE NOCASE,
        PRIMARY KEY(clip_id,tag)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_label ON clip_tags(tag,clip_id)")
    conn.execute("""CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        body BLOB NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )""")
    conn.execute("""CREATE TRIGGER IF NOT EXISTS clean_clip_tags
        AFTER DELETE ON clips BEGIN
            DELETE FROM clip_tags WHERE clip_id=OLD.id;
        END""")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(clips)")}
    if "touch_seq" not in columns:
        conn.execute(
            "ALTER TABLE clips ADD COLUMN touch_seq INTEGER NOT NULL DEFAULT 0"
        )
    if "fingerprint" not in columns:
        conn.execute("ALTER TABLE clips ADD COLUMN fingerprint BLOB")
    conn.execute("UPDATE clips SET touch_seq=id WHERE touch_seq=0")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_clips_bin_recent ON clips(bin,touch_seq)"
    )
    # All clips reads encrypted screenshot ciphertext in recency order.
    # Without this covering *order* index SQLite can materialize every
    # large ciphertext blob in a temporary B-tree before yielding a row.
    # The index stores metadata only; it never stores clip payloads.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_clips_global_recent "
        "ON clips(touch_seq DESC,id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_clips_bin_fingerprint ON clips(bin,fingerprint)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_clips_bin_id ON clips(bin,id)")
    # SQLite INTEGER PRIMARY KEY can reuse a deleted highest row ID.
    # Persist a monotonic allocation counter so stale dialogs/queue IDs
    # can never point to a different future clip.
    conn.execute("""CREATE TABLE IF NOT EXISTS clipmint_sequences (
        name TEXT PRIMARY KEY,
        next_id INTEGER NOT NULL CHECK(next_id > 0)
    )""")
    conn.execute(
        "INSERT OR IGNORE INTO clipmint_sequences(name,next_id) "
        "SELECT 'clips',COALESCE(MAX(id),0)+1 FROM clips"
    )
    conn.execute(
        "UPDATE clipmint_sequences SET next_id=MAX(next_id,"
        "(SELECT COALESCE(MAX(id),0)+1 FROM clips)) WHERE name='clips'"
    )
    conn.commit()
