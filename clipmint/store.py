"""Local SQLite clipboard history. Contents are not encrypted."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os
import sqlite3

@dataclass(frozen=True)
class Clip:
    id: int
    kind: str
    preview: str
    pinned: bool
    created_at: str

class ClipStore:
    def __init__(self, path: Path | None = None, max_unpinned: int = 250):
        if path is None:
            base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
            path = base / "clipmint" / "history.sqlite3"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_unpinned = max_unpinned
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS clips (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL CHECK(kind IN ('text', 'image')),
            content BLOB NOT NULL,
            preview TEXT NOT NULL,
            pinned INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT
                (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )""")
        self.conn.commit()

    def add(self, kind: str, content: bytes, preview: str) -> int | None:
        if kind not in ("text", "image"):
            raise ValueError("Unsupported clipboard type")
        if not content:
            return None
        newest = self.conn.execute(
            "SELECT id,kind,content FROM clips ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if newest and newest[1] == kind and newest[2] == content:
            return newest[0]
        cursor = self.conn.execute(
            "INSERT INTO clips(kind,content,preview) VALUES(?,?,?)",
            (kind, sqlite3.Binary(content), preview[:600])
        )
        self.conn.execute("""DELETE FROM clips WHERE pinned=0 AND id NOT IN
            (SELECT id FROM clips WHERE pinned=0 ORDER BY id DESC LIMIT ?)""",
            (self.max_unpinned,)
        )
        self.conn.commit()
        return cursor.lastrowid

    def search(self, query: str = "") -> list[Clip]:
        rows = self.conn.execute(
            """SELECT id,kind,preview,pinned,created_at FROM clips
               WHERE instr(lower(preview),lower(?)) > 0
               ORDER BY pinned DESC,id DESC LIMIT 500""",
            (query,)
        ).fetchall()
        return [Clip(r[0], r[1], r[2], bool(r[3]), r[4]) for r in rows]

    def get(self, clip_id: int) -> tuple[str, bytes] | None:
        row = self.conn.execute("SELECT kind,content FROM clips WHERE id=?", (clip_id,)).fetchone()
        return (row[0], bytes(row[1])) if row else None

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
        self.conn.close()
