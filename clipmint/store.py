"""Local SQLite clipboard history, organised into independent accumulation bins."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import sqlite3
from .clipboard_formats import bundle_to_bytes, bundle_from_bytes

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
    """Conservative opt-out for obvious credentials (not a security guarantee)."""
    return bool(re.search(r"(?i)\b(password|passwd|api[_ -]?key|secret[_ -]?key|access[_ -]?token)\s*[:=]\s*\S+", text))


class ClipStore:
    def __init__(self, path: Path | None = None, max_unpinned: int = 250):
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
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_clips_bin_id ON clips(bin,id)")
        self.conn.commit()

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
        self.conn.commit()
        return cursor.lastrowid

    def search(
        self, query: str = "", bin_name: str = "Work",
        sort: str = "Latest first", category: str = "All",
    ) -> list[Clip]:
        order = SORTS.get(sort, SORTS["Latest first"])
        rows = self.conn.execute(
            f"""SELECT id,kind,preview,pinned,created_at,bin FROM clips
               WHERE bin=? AND instr(lower(preview),lower(?)) > 0
               ORDER BY {order} LIMIT 1000""",
            (bin_name, query)
        ).fetchall()
        clips = [Clip(r[0], r[1], r[2], bool(r[3]), r[4], r[5]) for r in rows]
        if category != "All":
            clips = [clip for clip in clips if classify(clip) == category]
        return clips

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
        self.conn.execute("DELETE FROM clips WHERE id=?", (clip_id,))
        self.conn.commit()

    def close(self) -> None:
        if not self.closed:
            self.conn.close()
            self.closed = True
