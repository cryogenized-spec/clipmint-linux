"""Local SQLite clipboard history, organised into independent accumulation bins."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import sqlite3
from .clipboard_formats import bundle_to_bytes, bundle_from_bytes
from .secret_detector import detect_secret
from .search_index import ClipSearchIndex

DEFAULT_BINS = ("Work", "Personal", "Temporary")
SORTS = {
    "Latest first": "id DESC",
    "Oldest first": "id ASC",
    "A–Z": "preview COLLATE NOCASE ASC, id DESC",
    "Z–A": "preview COLLATE NOCASE DESC, id DESC",
    "Numbered list": "id DESC",
}


@dataclass(frozen=True)
class Clip:
    id: int
    kind: str
    preview: str
    pinned: bool
    created_at: str
    bin: str = "Work"
    favorite: bool = False


def classify(clip: Clip) -> str:
    if clip.kind == "files":
        return "Files"
    if clip.kind == "image":
        return "Images"
    text = clip.preview.strip()
    if re.search(r"https?://|www\.", text, flags=re.I):
        return "URLs"
    if re.fullmatch(r"\+?[\d\s()\-.]{7,22}", text) and sum(ch.isdigit() for ch in text) >= 7:
        return "Phone numbers"
    return "Text"


def looks_sensitive(text: str) -> bool:
    """Compatibility entry point for the shared secret detector."""
    return detect_secret(text).is_secret


class ClipStore:
    def __init__(self, path: Path | None = None, max_unpinned: int = 250,
                 index_plaintext: bool = True):
        if path is None:
            base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
            path = base / "clipmint" / "history.sqlite3"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_unpinned = max_unpinned
        self.closed = False
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS clips (
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
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(clips)")}
        if "formats" not in columns:
            self.conn.execute("ALTER TABLE clips ADD COLUMN formats BLOB")
        if "bin" not in columns:
            self.conn.execute("ALTER TABLE clips ADD COLUMN bin TEXT NOT NULL DEFAULT 'Work'")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS bins (
            name TEXT PRIMARY KEY,
            position INTEGER NOT NULL
        )""")
        for index, name in enumerate(DEFAULT_BINS):
            self.conn.execute("INSERT OR IGNORE INTO bins(name,position) VALUES(?,?)", (name, index))
        original_schema = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='clips'"
        ).fetchone()[0]
        if "'files'" not in original_schema:
            # Original v0.3 database CHECK only permitted text/images. Rebuild
            # transactionally, retaining row IDs, timestamps, pins and bins.
            # Any failure rolls the whole migration back rather than dropping
            # or silently rewriting user history.
            self.conn.execute("SAVEPOINT clipmint_mime_upgrade")
            try:
                self.conn.execute("""CREATE TABLE clips_mime_upgrade (
                    id INTEGER PRIMARY KEY,
                    kind TEXT NOT NULL CHECK(kind IN ('text','image','files')),
                    content BLOB NOT NULL, formats BLOB, preview TEXT NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT
                      (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    bin TEXT NOT NULL DEFAULT 'Work'
                )""")
                self.conn.execute("""INSERT INTO clips_mime_upgrade
                    (id,kind,content,formats,preview,pinned,created_at,bin)
                    SELECT id,kind,content,formats,preview,pinned,created_at,bin
                    FROM clips""")
                self.conn.execute("DROP TABLE clips")
                self.conn.execute("ALTER TABLE clips_mime_upgrade RENAME TO clips")
                self.conn.execute("RELEASE SAVEPOINT clipmint_mime_upgrade")
            except Exception:
                self.conn.execute("ROLLBACK TO SAVEPOINT clipmint_mime_upgrade")
                self.conn.execute("RELEASE SAVEPOINT clipmint_mime_upgrade")
                raise
        # Non-destructive metadata migration. Favourites and labels are
        # intentionally separate from pinning/retention protection.
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(clips)")}
        if "favorite" not in columns:
            self.conn.execute("ALTER TABLE clips ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS clip_tags (
            clip_id INTEGER NOT NULL, tag TEXT NOT NULL COLLATE NOCASE,
            PRIMARY KEY(clip_id,tag)
        )""")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_label ON clip_tags(tag,clip_id)")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            body BLOB NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )""")
        self.conn.execute("""CREATE TRIGGER IF NOT EXISTS clean_clip_tags
            AFTER DELETE ON clips BEGIN
                DELETE FROM clip_tags WHERE clip_id=OLD.id;
            END""")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_clips_bin_id ON clips(bin,id)")
        self.conn.commit()
        self.search_index = ClipSearchIndex(self.conn, enabled=index_plaintext)

    def bins(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT name FROM bins ORDER BY position,name")]

    def add_bin(self, name: str) -> None:
        name = name.strip()
        if not name or len(name) > 32:
            raise ValueError("Bin name must have 1–32 characters")
        self.conn.execute("INSERT INTO bins(name,position) VALUES(?,COALESCE((SELECT MAX(position)+1 FROM bins),0))", (name,))
        self.conn.commit()

    def add(self, kind: str, content: bytes, preview: str, bin_name: str = "Work",
            formats: dict[str, bytes] | None = None) -> int | None:
        if kind not in ("text", "image", "files"):
            raise ValueError("Unsupported clipboard type")
        if bin_name not in self.bins():
            raise ValueError("Unknown accumulation bin")
        if not content:
            return None
        # Protect direct writes as well as interactive clipboard capture.
        if kind == "text":
            if detect_secret(content.decode("utf-8", "replace")).is_secret:
                return None
            for mime, raw in (formats or {}).items():
                if mime in ("text/html", "text/plain", "text/plain;charset=utf-8"):
                    if detect_secret(raw.decode("utf-8", "replace")).is_secret:
                        return None
        packed = bundle_to_bytes(formats) if formats else None
        newest = self.conn.execute(
            "SELECT id,kind,content,formats FROM clips WHERE bin=? ORDER BY id DESC LIMIT 1", (bin_name,)
        ).fetchone()
        if newest and newest[1] == kind and newest[2] == content and newest[3] == packed:
            return newest[0]
        cursor = self.conn.execute(
            "INSERT INTO clips(kind,content,preview,bin,formats) VALUES(?,?,?,?,?)",
            (kind, sqlite3.Binary(content), preview[:600], bin_name,
             sqlite3.Binary(packed) if packed is not None else None)
        )
        # Each bin retains its own pinned items and most recent unpinned items.
        self.conn.execute("""DELETE FROM clips WHERE bin=? AND pinned=0 AND id NOT IN
            (SELECT id FROM clips WHERE bin=? AND pinned=0 ORDER BY id DESC LIMIT ?)""",
            (bin_name, bin_name, self.max_unpinned)
        )
        self.search_index.insert(cursor.lastrowid, kind, content, preview[:600])
        self.search_index.trim_deleted()
        self.conn.commit()
        return cursor.lastrowid

    def search(
        self, query: str = "", bin_name: str = "Work",
        sort: str = "Latest first", category: str = "All",
        tag: str = "", favorites_only: bool = False,
    ) -> list[Clip]:
        """Search indexed clip bodies and previews; retain literal fallback.

        Existing list sorting and punctuation searches remain compatible.
        A separate 'Best match' sort uses bm25() ranking from SQLite FTS5.
        """
        sort = sort if sort in SORTS or sort == "Best match" else "Latest first"
        order = SORTS.get(sort, "id DESC")
        query = str(query)[:256]
        matched_ids = self.search_index.search_ids(query, bin_name) if query.strip() else []
        params: list[object] = [bin_name]
        where = ["bin=?"]
        if query:
            if matched_ids:
                slots = ",".join("?" for _ in matched_ids)
                where.append(
                    f"(id IN ({slots}) OR instr(lower(preview),lower(?)) > 0)"
                )
                params.extend(matched_ids)
                params.append(query)
            else:
                where.append("instr(lower(preview),lower(?)) > 0")
                params.append(query)
        if favorites_only:
            where.append("favorite=1")
        if tag:
            where.append("""EXISTS (SELECT 1 FROM clip_tags t
                          WHERE t.clip_id=clips.id AND t.tag=?)""")
            params.append(tag.lower().strip())
        rows = self.conn.execute(
            f"""SELECT id,kind,preview,pinned,created_at,bin,favorite FROM clips
                WHERE {' AND '.join(where)} ORDER BY {order} LIMIT 1000""",
            params
        ).fetchall()
        clips = [Clip(r[0],r[1],r[2],bool(r[3]),r[4],r[5],bool(r[6])) for r in rows]
        if category != "All":
            clips = [clip for clip in clips if classify(clip) == category]
        if sort == "Best match" and query:
            relevance = {ident: i for i, ident in enumerate(matched_ids)}
            clips.sort(key=lambda c: (relevance.get(c.id, 10**7), -c.id))
        return clips

    def index_status(self) -> str:
        return "SQLite FTS5 · Indexed full text" if self.search_index.enabled else "Literal preview search"

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

    def count(self, bin_name: str) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM clips WHERE bin=?", (bin_name,)).fetchone()[0]

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

    def close(self) -> None:
        if not self.closed:
            self.conn.close()
            self.closed = True
