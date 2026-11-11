"""Explicit, opt-in SQLite retention and compaction service.

Storage deletion policy stays unchanged: byte pruning is OFF until selected;
Temporary expiry / quit cleanup require separate user choices, and pinned
entries remain protected. This service never opens or closes a connection.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

from .search_index import ClipSearchIndex


class HistoryRetentionService:
    def __init__(self, conn: sqlite3.Connection, search_index: ClipSearchIndex):
        self.conn = conn
        self.search_index = search_index

    def payload_bytes(self) -> int:
        """Approximate stored payload sizes, including MIME and previews."""
        return int(self.conn.execute(
            "SELECT COALESCE(SUM(length(content)+COALESCE(length(formats),0)"
            "+length(CAST(preview AS BLOB))),0) FROM clips"
        ).fetchone()[0])

    def prune_storage_bytes(self, limit: int | None) -> int:
        """Opt-in LRU pruning; pinned entries are never removed.

        Does not VACUUM or imply that historical pages were physically erased.
        """
        if limit is None:
            return 0
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("Retention byte cap must be a positive integer")
        removed = 0
        while self.payload_bytes() > limit:
            row = self.conn.execute(
                "SELECT id FROM clips WHERE pinned=0 "
                "ORDER BY touch_seq ASC,id ASC LIMIT 1"
            ).fetchone()
            if row is None:
                break  # Pinned payloads alone can exceed the selected cap.
            ident = int(row[0])
            self.search_index.delete(ident)
            self.conn.execute("DELETE FROM clips WHERE id=?", (ident,))
            removed += 1
        if removed:
            self.search_index.trim_deleted()
            self.conn.commit()
        return removed

    def refresh_temporary_copy_time(self, clip_id: int) -> None:
        """Refresh TTL after a user copies an entry from ClipMint's history.

        Clipboard reinsertion is intentionally suppressed on these paths, so
        history-copy actions must refresh the original item's retention clock.
        Pinned clips are also touched, preserving freshness if later unpinned.
        Other bins remain unaffected.
        """
        with self.conn:
            self.conn.execute(
                "UPDATE clips SET created_at="
                "strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                "WHERE id=? AND bin='Temporary'",
                (clip_id,),
            )

    def _remove_temporary_unpinned(
        self, cutoff_iso: str | None = None,
        deleted_ids: list[int] | None = None,
    ) -> int:
        """Delete only unpinned clips in the built-in Temporary collection.

        A cutoff of None is reserved for an explicitly enabled normal-exit
        cleanup. A timestamp is used for opt-in age-based expiration.
        Pinned items, reusable templates, and other bins are not touched.
        """
        condition = "bin='Temporary' AND pinned=0"
        parameters: tuple[str, ...] = ()
        if cutoff_iso is not None:
            # julianday ignores malformed/unknown timestamps (NULL), so
            # legacy rows without a valid UTC date are not purged blindly.
            condition += " AND julianday(created_at) <= julianday(?)"
            parameters = (cutoff_iso,)
        identifiers = [int(row[0]) for row in self.conn.execute(
            "SELECT id FROM clips WHERE " + condition, parameters
        )]
        if not identifiers:
            return 0
        with self.conn:
            for ident in identifiers:
                self.search_index.delete(ident)
            self.conn.executemany(
                "DELETE FROM clips WHERE id=? AND bin='Temporary' AND pinned=0",
                [(ident,) for ident in identifiers],
            )
            self.search_index.trim_deleted()
        # Report committed removals before any optional compaction. Even if
        # SQLite VACUUM fails, consumers must invalidate stale clip IDs.
        if deleted_ids is not None:
            deleted_ids.extend(identifiers)
        # FTS5 can retain deleted terms in shadow posting segments even after
        # the MATCH index no longer reports them. Rebuild surviving postings,
        # then reconstruct SQLite pages instead of retaining old free space.
        if self.search_index.enabled:
            self.search_index.rebuild_after_purge()
            self.conn.execute("VACUUM")
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return len(identifiers)

    def expire_temporary_unpinned(
        self, *, now: datetime | None = None,
        deleted_ids: list[int] | None = None,
    ) -> int:
        """Opt-in 24-hour TTL; the caller decides whether it is enabled."""
        current = datetime.now(timezone.utc) if now is None else now
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("Temporary retention requires an aware UTC timestamp")
        cutoff = current.astimezone(timezone.utc) - timedelta(hours=24)
        return self._remove_temporary_unpinned(
            cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            deleted_ids=deleted_ids,
        )

    def clear_temporary_unpinned(
        self, *, deleted_ids: list[int] | None = None,
    ) -> int:
        """Run only on deliberate application exit with explicit user opt-in."""
        return self._remove_temporary_unpinned(deleted_ids=deleted_ids)

    def compact_history(self) -> None:
        """Explicit user-initiated compaction; may use CPU on large histories."""
        self.conn.commit()
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.conn.execute("VACUUM")
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
