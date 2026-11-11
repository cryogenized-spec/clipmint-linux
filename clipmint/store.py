"""Local SQLite clipboard history, organised into independent accumulation bins."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import os
import re
import sqlite3
import stat
from .clipboard_formats import bundle_to_bytes, bundle_from_bytes, sensitive_payload
from .secret_detector import detect_secret
from .search_index import ClipSearchIndex
from .clip_model import DEFAULT_BINS, SORTS, Clip, classify
from .history_search import HistorySearchService
from .history_schema import initialize_history_schema
from .history_retention import HistoryRetentionService

def looks_sensitive(text: str) -> bool:
    """Compatibility entry point for the shared secret detector."""
    return detect_secret(text).is_secret


class ClipStore:
    def __init__(self, path: Path | None = None, max_unpinned: int = 250,
                 index_plaintext: bool = True, max_total_bytes: int | None = None):
        managed_path = path is None
        if path is None:
            base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
            path = base / "clipmint" / "history.sqlite3"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if managed_path:
            os.chmod(self.path.parent, 0o700)
        # Refuse final-component symlink redirects, then enforce owner-only DB
        # permissions on both new and upgraded history databases.
        fd = os.open(
            self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("Clipboard history path is not a regular file")
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        self.max_unpinned = max_unpinned
        self.max_total_bytes = max_total_bytes  # None means OFF, never prune on upgrade
        self.closed = False
        self.conn = sqlite3.connect(self.path)
        initialize_history_schema(self.conn)
        self.search_index = ClipSearchIndex(self.conn, enabled=index_plaintext)
        self._history_search = HistorySearchService(self.conn, self.search_index)
        self._retention = HistoryRetentionService(self.conn, self.search_index)

    def bins(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT name FROM bins ORDER BY position,name")]

    def add_bin(self, name: str) -> None:
        name = name.strip()
        if not name or len(name) > 32:
            raise ValueError("Bin name must have 1–32 characters")
        # A duplicate name or other SQLite error must not leave an open
        # transaction that blocks later history exports.
        with self.conn:
            self.conn.execute(
                "INSERT INTO bins(name,position) "
                "VALUES(?,COALESCE((SELECT MAX(position)+1 FROM bins),0))",
                (name,),
            )

    def _allocate_clip_id(self) -> int:
        # Called only within an insertion transaction. Legacy encrypted
        # migration may insert explicit IDs, so account for the current max.
        row = self.conn.execute(
            "SELECT next_id FROM clipmint_sequences WHERE name='clips'"
        ).fetchone()
        next_id = max(
            int(row[0]),
            int(self.conn.execute(
                "SELECT COALESCE(MAX(id),0)+1 FROM clips"
            ).fetchone()[0]),
        )
        self.conn.execute(
            "UPDATE clipmint_sequences SET next_id=? WHERE name='clips'",
            (next_id + 1,),
        )
        return next_id

    @staticmethod
    def _fingerprint(kind: str, content: bytes, packed: bytes | None) -> bytes:
        """Stable content identity for normal plaintext history."""
        digest = hashlib.sha256()
        digest.update(kind.encode("ascii") + b"\\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        digest.update(packed or b"")
        return digest.digest()

    def _next_touch_seq(self) -> int:
        return self.conn.execute(
            "SELECT COALESCE(MAX(touch_seq),0)+1 FROM clips"
        ).fetchone()[0]

    def _touch_duplicate(self, ident: int, fingerprint: bytes) -> int:
        self.conn.execute(
            """UPDATE clips SET touch_seq=?, fingerprint=?,
                 created_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""",
            (self._next_touch_seq(), sqlite3.Binary(fingerprint), ident)
        )
        self.conn.commit()
        return ident

    def _find_plain_duplicate(
        self, kind: str, content: bytes, packed: bytes | None,
        bin_name: str, fingerprint: bytes,
    ) -> int | None:
        # All new entries have a fingerprint. Pre-upgrade entries have NULL
        # and are checked byte-for-byte, then lazily receive the fingerprint.
        for ident, older_content, older_formats in self.conn.execute(
            "SELECT id,content,formats FROM clips "
            "WHERE bin=? AND kind=? AND fingerprint=? ORDER BY touch_seq DESC",
            (bin_name, kind, sqlite3.Binary(fingerprint))
        ):
            if bytes(older_content) == content and (
                bytes(older_formats) if older_formats is not None else None
            ) == packed:
                return ident
        for ident, older_content, older_formats in self.conn.execute(
            "SELECT id,content,formats FROM clips "
            "WHERE bin=? AND kind=? AND fingerprint IS NULL",
            (bin_name, kind)
        ):
            if bytes(older_content) == content and (
                bytes(older_formats) if older_formats is not None else None
            ) == packed:
                return ident
        return None

    def _history_payload_is_sealed(self) -> bool:
        """Encrypted history validates cleartext before sealing."""
        return False

    def add(
        self, kind: str, content: bytes, preview: str, bin_name: str = "Work",
        formats: dict[str, bytes] | None = None, *,
        _sealed_fingerprint: bytes | None = None,
    ) -> int | None:
        if kind not in ("text", "image", "files"):
            raise ValueError("Unsupported clipboard type")
        if bin_name not in self.bins():
            raise ValueError("Unknown accumulation bin")
        if not content:
            return None
        # Check plaintext direct writes. EncryptedClipStore checks sensitive
        # payloads BEFORE encrypting; ciphertext must never be classified.
        if (not self._history_payload_is_sealed()
                and sensitive_payload(kind, content, formats)):
            return None
        packed = bundle_to_bytes(formats) if formats else None
        fingerprint = (_sealed_fingerprint if _sealed_fingerprint is not None
                       else self._fingerprint(kind, content, packed))
        if _sealed_fingerprint is None:
            previous = self._find_plain_duplicate(
                kind, content, packed, bin_name, fingerprint
            )
            if previous is not None:
                return self._touch_duplicate(previous, fingerprint)
        # Retention's monotonic IDs prevent stale queue entries resolving to
        # another clip after deletion; dedup recency is tracked separately.
        clip_id = self._allocate_clip_id()
        self.conn.execute(
            """INSERT INTO clips
               (id,kind,content,preview,bin,formats,touch_seq,fingerprint)
               VALUES(?,?,?,?,?,?,?,?)""",
            (clip_id, kind, sqlite3.Binary(content), preview[:600], bin_name,
             sqlite3.Binary(packed) if packed is not None else None,
             self._next_touch_seq(), sqlite3.Binary(fingerprint))
        )
        self.conn.execute("""DELETE FROM clips WHERE bin=? AND pinned=0 AND id NOT IN
            (SELECT id FROM clips WHERE bin=? AND pinned=0
             ORDER BY touch_seq DESC,id DESC LIMIT ?)""",
            (bin_name, bin_name, self.max_unpinned)
        )
        self.search_index.insert(clip_id, kind, content, preview[:600])
        self.search_index.trim_deleted()
        self.prune_storage_bytes()
        self.conn.commit()
        return clip_id if self.conn.execute(
            "SELECT 1 FROM clips WHERE id=?", (clip_id,)
        ).fetchone() else None

    def payload_bytes(self) -> int:
        return self._retention.payload_bytes()

    def prune_storage_bytes(self) -> int:
        return self._retention.prune_storage_bytes(self.max_total_bytes)

    def _best_match_records(
        self, query: str, bin_name: str | None, category: str,
        tag: str, favorites_only: bool,
    ) -> list[Clip]:
        """Compatibility facade for ranked metadata-only history search."""
        return self._history_search._best_match_records(
            query, bin_name, category, tag, favorites_only
        )

    def search(
        self, query: str = "", bin_name: str | None = "Work",
        sort: str = "Latest first", category: str = "All",
        tag: str = "", favorites_only: bool = False,
    ) -> list[Clip]:
        """Delegate to search service without opening another connection."""
        return self._history_search.search(
            query, bin_name, sort, category, tag, favorites_only
        )

    def index_status(self) -> str:
        return self._history_search.index_status()

    def favorite(self, clip_id: int, enabled: bool) -> None:
        self.conn.execute("UPDATE clips SET favorite=? WHERE id=?", (int(enabled), clip_id))
        self.conn.commit()

    def is_favorite(self, clip_id: int) -> bool:
        row = self.conn.execute("SELECT favorite FROM clips WHERE id=?", (clip_id,)).fetchone()
        return bool(row[0]) if row else False

    def tags(self, clip_id: int) -> list[str]:
        return [r[0] for r in self.conn.execute(
            "SELECT tag FROM clip_tags WHERE clip_id=? ORDER BY tag COLLATE NOCASE", (clip_id,)
        )]

    def all_tags(self) -> list[str]:
        return [r[0] for r in self.conn.execute(
            "SELECT DISTINCT tag FROM clip_tags ORDER BY tag COLLATE NOCASE"
        )]

    def set_tags(self, clip_id: int, values: list[str]) -> None:
        if self.get(clip_id) is None:
            raise ValueError("Clipboard entry no longer exists")
        tags = []
        for value in values:
            tag = value.strip().lower()
            if not tag or len(tag) > 32 or not re.fullmatch(r"[\w-]+", tag, re.UNICODE):
                raise ValueError("Tags must be 1–32 letters, numbers, underscores or hyphens")
            if tag not in tags:
                tags.append(tag)
        if len(tags) > 15:
            raise ValueError("A clip may have at most 15 tags")
        with self.conn:
            self.conn.execute("DELETE FROM clip_tags WHERE clip_id=?", (clip_id,))
            self.conn.executemany(
                "INSERT INTO clip_tags(clip_id,tag) VALUES(?,?)",
                [(clip_id, tag) for tag in tags]
            )

    def _encode_template(self, text: str) -> bytes:
        return text.encode("utf-8")

    def _decode_template(self, value: bytes) -> str:
        return bytes(value).decode("utf-8")

    def save_template(self, name: str, body: str, template_id: int | None = None) -> int:
        name = name.strip()
        if not name or len(name) > 80:
            raise ValueError("Template name must have 1–80 characters")
        if not body or len(body.encode("utf-8")) > 32768:
            raise ValueError("Template must contain 1–32 KiB of text")
        encoded = sqlite3.Binary(self._encode_template(body))
        with self.conn:
            if template_id is None:
                row = self.conn.execute(
                    "INSERT INTO templates(name,body) VALUES(?,?)", (name,encoded)
                )
                return row.lastrowid
            result = self.conn.execute(
                "UPDATE templates SET name=?,body=? WHERE id=?",
                (name,encoded,template_id)
            )
            if not result.rowcount:
                raise ValueError("Template not found")
            return template_id

    def templates(self) -> list[tuple[int, str, str]]:
        return [(r[0],r[1],self._decode_template(bytes(r[2])))
                for r in self.conn.execute(
                    "SELECT id,name,body FROM templates ORDER BY name COLLATE NOCASE"
                )]

    def delete_template(self, template_id: int) -> None:
        self.conn.execute("DELETE FROM templates WHERE id=?", (template_id,))
        self.conn.commit()

    def count(self, bin_name: str | None) -> int:
        if bin_name is None:
            return int(self.conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0])
        return int(self.conn.execute(
            "SELECT COUNT(*) FROM clips WHERE bin=?", (bin_name,)
        ).fetchone()[0])

    def refresh_temporary_copy_time(self, clip_id: int) -> None:
        return self._retention.refresh_temporary_copy_time(clip_id)

    def _remove_temporary_unpinned(
        self, cutoff_iso: str | None = None,
        deleted_ids: list[int] | None = None,
    ) -> int:
        return self._retention._remove_temporary_unpinned(
            cutoff_iso, deleted_ids,
        )

    def expire_temporary_unpinned(
        self, *, now: datetime | None = None,
        deleted_ids: list[int] | None = None,
    ) -> int:
        return self._retention.expire_temporary_unpinned(
            now=now, deleted_ids=deleted_ids,
        )

    def clear_temporary_unpinned(
        self, *, deleted_ids: list[int] | None = None,
    ) -> int:
        return self._retention.clear_temporary_unpinned(
            deleted_ids=deleted_ids,
        )

    def move(self, clip_id: int, bin_name: str) -> None:
        if bin_name not in self.bins():
            raise ValueError("Unknown accumulation bin")
        self.conn.execute("UPDATE clips SET bin=? WHERE id=?", (bin_name, clip_id))
        self.conn.commit()

    def get(self, clip_id: int) -> tuple[str, bytes] | None:
        row = self.conn.execute("SELECT kind,content FROM clips WHERE id=?", (clip_id,)).fetchone()
        return (row[0], bytes(row[1])) if row else None

    def get_formats(self, clip_id: int) -> dict[str, bytes]:
        row = self.conn.execute("SELECT formats FROM clips WHERE id=?", (clip_id,)).fetchone()
        return bundle_from_bytes(bytes(row[0]) if row and row[0] is not None else None)

    def pin(self, clip_id: int, enabled: bool) -> None:
        self.conn.execute("UPDATE clips SET pinned=? WHERE id=?", (int(enabled), clip_id))
        self.conn.commit()

    def pinned(self, clip_id: int) -> bool:
        row = self.conn.execute("SELECT pinned FROM clips WHERE id=?", (clip_id,)).fetchone()
        return bool(row[0]) if row else False

    def delete(self, clip_id: int) -> None:
        self.search_index.delete(clip_id)
        self.conn.execute("DELETE FROM clips WHERE id=?", (clip_id,))
        self.conn.commit()
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def compact_history(self) -> None:
        return self._retention.compact_history()

    def close(self) -> None:
        if not self.closed:
            self.conn.commit()
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.conn.close()
            self.closed = True
