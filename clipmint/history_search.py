"""Metadata-only history searching for the ordinary SQLite store.

Search receives its connection and index through ClipStore; it never opens
new database connections, bypasses retention, or loads clipboard payloads.
EncryptedClipStore continues to override search with in-memory matching.
"""
from __future__ import annotations

from .clip_model import Clip, SORTS
from .search_index import safe_fts_query


class HistorySearchMixin:
    """Search implementation kept separate from persistence and migrations."""

    def _best_match_records(
        self, query: str, bin_name: str | None, category: str,
        tag: str, favorites_only: bool,
    ) -> list[Clip]:
        """Rank filtered full-text matches BEFORE limiting displayed records.

        Only ID and preview metadata are loaded; clipboard payloads are never
        materialized during search. Literal-preview matches remain a fallback.
        """
        ranked_ids = self.search_index.search_ids(
            query, bin_name, category=category, tag=tag,
            favorites_only=favorites_only,
        )
        by_id: dict[int, Clip] = {}
        for start in range(0, len(ranked_ids), 400):
            part = ranked_ids[start:start + 400]
            slots = ",".join("?" for _ in part)
            rows = self.conn.execute(
                "SELECT id,kind,preview,pinned,created_at,bin,favorite "
                "FROM clips WHERE id IN (" + slots + ")", part,
            )
            for row in rows:
                by_id[row[0]] = Clip(
                    row[0], row[1], row[2], bool(row[3]), row[4],
                    row[5], bool(row[6]),
                )
        clips = [by_id[ident] for ident in ranked_ids if ident in by_id]
        if len(clips) >= 1000:
            return clips[:1000]
        # Literal fallbacks matter for punctuation and Unicode substring
        # searches that do not tokenize as the FTS expression does.
        where = ["instr(lower(preview),lower(?)) > 0"]
        params: list[object] = [query]
        if bin_name is not None:
            where.append("bin=?")
            params.append(bin_name)
        if category != "All":
            where.append("clipmint_category(kind,preview)=?")
            params.append(category)
        if favorites_only:
            where.append("favorite=1")
        if tag:
            where.append(
                "EXISTS (SELECT 1 FROM clip_tags t "
                "WHERE t.clip_id=clips.id AND t.tag=?)"
            )
            params.append(tag.lower().strip())
        params.append(1000)
        rows = self.conn.execute(
            "SELECT id,kind,preview,pinned,created_at,bin,favorite "
            "FROM clips WHERE " + " AND ".join(where) +
            " ORDER BY touch_seq DESC,id DESC LIMIT ?", params,
        )
        used = set(by_id)
        for row in rows:
            if row[0] in used:
                continue
            clips.append(Clip(
                row[0], row[1], row[2], bool(row[3]), row[4],
                row[5], bool(row[6]),
            ))
            if len(clips) >= 1000:
                break
        return clips

    def search(
        self, query: str = "", bin_name: str | None = "Work",
        sort: str = "Latest first", category: str = "All",
        tag: str = "", favorites_only: bool = False,
    ) -> list[Clip]:
        """Search indexed clip bodies and previews; retain literal fallback.

        Existing list sorting and punctuation searches remain compatible.
        A separate 'Best match' sort uses bm25() ranking from SQLite FTS5.
        """
        sort = sort if sort in SORTS or sort == "Best match" else "Latest first"
        order = SORTS.get(sort, "touch_seq DESC, id DESC")
        query = str(query)[:256]
        # Use an FTS subquery *inside* the filtered SQL rather than a
        # separately limited candidate list. With multiple Autosort bins,
        # an older favourite/tagged match must not disappear behind 1,000
        # more recent full-body matches in other collections.
        fts_query = (safe_fts_query(query) if self.search_index.enabled else "")
        if sort == "Best match" and query.strip() and fts_query:
            return self._best_match_records(
                query, bin_name, category, tag, favorites_only,
            )
        # None is an explicit all-collections view, not a physical bin.
        # This retains the usual active-bin filtering for existing callers.
        params: list[object] = [] if bin_name is None else [bin_name]
        where = [] if bin_name is None else ["bin=?"]
        if query:
            if fts_query:
                where.append(
                    "(id IN (SELECT rowid FROM clipmint_fts "
                    "WHERE clipmint_fts MATCH ?) "
                    "OR instr(lower(preview),lower(?)) > 0)"
                )
                params.extend((fts_query, query))
            else:
                where.append("instr(lower(preview),lower(?)) > 0")
                params.append(query)
        if category != "All":
            where.append("clipmint_category(kind,preview)=?")
            params.append(category)
        if favorites_only:
            where.append("favorite=1")
        if tag:
            where.append("""EXISTS (SELECT 1 FROM clip_tags t
                          WHERE t.clip_id=clips.id AND t.tag=?)""")
            params.append(tag.lower().strip())
        rows = self.conn.execute(
            f"""SELECT id,kind,preview,pinned,created_at,bin,favorite FROM clips
                {('WHERE ' + ' AND '.join(where)) if where else ''}
                ORDER BY {order} LIMIT 1000""",
            params
        ).fetchall()
        clips = [Clip(r[0],r[1],r[2],bool(r[3]),r[4],r[5],bool(r[6])) for r in rows]
        return clips

    def index_status(self) -> str:
        return "SQLite FTS5 · Indexed full text" if self.search_index.enabled else "Literal preview search"

