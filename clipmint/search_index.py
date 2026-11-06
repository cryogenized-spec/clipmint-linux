"""Optional SQLite FTS5 index for ordinary (unencrypted) clipboard history.

Index full plain-text clip bodies up to 128 KiB, not merely the 600-character
list preview. The index never runs for EncryptedClipStore: creating a plaintext
FTS database for encrypted history would undermine its protections.

All FTS MATCH queries are built from quoted Unicode word tokens, not raw SQL,
and retain the legacy substring fallback for punctuation and partial snippets.
"""
from __future__ import annotations

import re
import sqlite3

MAX_INDEX_CHARS = 131_072
MAX_RESULTS = 1000
_WORD = re.compile(r"\w+", re.UNICODE)


def safe_fts_query(query: str) -> str:
    """Prefix-match every word; never pass untrusted MATCH syntax through."""
    tokens = _WORD.findall(query[:256])
    if not tokens:
        return ""
    return " AND ".join('"' + token.replace('"', '""') + '"*' for token in tokens[:12])


class ClipSearchIndex:
    def __init__(self, conn: sqlite3.Connection, enabled: bool = True):
        self.conn = conn
        self.enabled = False
        if not enabled:
            return
        try:
            self.conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS clipmint_fts
                USING fts5(preview, body, tokenize='unicode61 remove_diacritics 2')""")
            self.enabled = True
            self._repair_if_needed()
        except sqlite3.OperationalError as exc:
            # Some custom SQLite builds omit FTS5; ordinary substring search
            # remains available and no data is lost.
            if "fts5" not in str(exc).lower() and "no such module" not in str(exc).lower():
                raise
            self.enabled = False

    @staticmethod
    def body_text(kind: str, content: bytes) -> str:
        if kind != "text":
            return ""
        return bytes(content[:MAX_INDEX_CHARS * 4]).decode("utf-8", "replace")[:MAX_INDEX_CHARS]

    def _repair_if_needed(self):
        clips = self.conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        indexed = self.conn.execute("SELECT COUNT(*) FROM clipmint_fts").fetchone()[0]
        if clips == indexed:
            return
        self.conn.execute("DELETE FROM clipmint_fts")
        for ident, kind, content, preview in self.conn.execute(
            "SELECT id,kind,content,preview FROM clips"
        ):
            self.conn.execute(
                "INSERT INTO clipmint_fts(rowid,preview,body) VALUES(?,?,?)",
                (ident, preview, self.body_text(kind, bytes(content)))
            )
        self.conn.commit()

    def insert(self, ident: int, kind: str, content: bytes, preview: str):
        if not self.enabled:
            return
        self.conn.execute("DELETE FROM clipmint_fts WHERE rowid=?", (ident,))
        self.conn.execute(
            "INSERT INTO clipmint_fts(rowid,preview,body) VALUES(?,?,?)",
            (ident, preview, self.body_text(kind, content))
        )

    def delete(self, ident: int):
        if self.enabled:
            self.conn.execute("DELETE FROM clipmint_fts WHERE rowid=?", (ident,))

    def trim_deleted(self):
        if self.enabled:
            self.conn.execute(
                "DELETE FROM clipmint_fts WHERE rowid NOT IN (SELECT id FROM clips)"
            )

    def rebuild_after_purge(self) -> None:
        """Rewrite FTS5 segments from surviving rows after retention cleanup.

        Merely deleting MATCH rows can leave old terms in the FTS5 shadow
        index until it is compacted. The caller performs VACUUM afterward
        to discard obsolete database pages. This is not SSD secure erasure.
        """
        if not self.enabled:
            return
        with self.conn:
            self.conn.execute("DELETE FROM clipmint_fts")
            for ident, kind, content, preview in self.conn.execute(
                "SELECT id,kind,content,preview FROM clips"
            ):
                self.conn.execute(
                    "INSERT INTO clipmint_fts(rowid,preview,body) VALUES(?,?,?)",
                    (ident, preview, self.body_text(kind, bytes(content))),
                )
            self.conn.execute(
                "INSERT INTO clipmint_fts(clipmint_fts) VALUES('optimize')"
            )

    def search_ids(self, query: str, bin_name: str | None) -> list[int]:
        if not self.enabled:
            return []
        expression = safe_fts_query(query)
        if not expression:
            return []
        try:
            # The all-collections view is explicit. Never interpolate a
            # clipboard-supplied string or a bin label into SQL.
            condition = "" if bin_name is None else " AND clips.bin=?"
            params = ((expression, MAX_RESULTS) if bin_name is None
                      else (expression, bin_name, MAX_RESULTS))
            rows = self.conn.execute(
                "SELECT clipmint_fts.rowid FROM clipmint_fts "
                "JOIN clips ON clips.id=clipmint_fts.rowid "
                "WHERE clipmint_fts MATCH ?" + condition +
                " ORDER BY bm25(clipmint_fts) LIMIT ?",
                params
            )
            return [int(row[0]) for row in rows]
        except sqlite3.OperationalError:
            # Never interpret a malformed or unsupported search as an SQLite
            # statement; the caller can still do literal preview search.
            return []
