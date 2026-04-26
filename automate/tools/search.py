"""Coze-style hybrid retrieval — SQLite FTS5 + structured filters.

The user reported that vector-only retrieval ("Plot Ode") was unusable in
practice. Coze gets it right because it runs BM25 (keyword) + vector +
re-ranking; the BM25 half catches proper nouns and IDs that embeddings
miss. We ship the BM25 half today (free, zero deps via SQLite FTS5) and
leave room for an embeddings adapter later.

The agent prefers ``search.find`` over ``notes.search`` / ``files.list``
when the user is looking for *something specific* — an item by name, a
date range, or a tag — instead of a generic listing.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from ..store import get_db
from .registry import Tool, ToolRegistry


def _to_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        if "T" not in value and " " not in value:
            value = value + "T00:00"
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _fts_query(raw: str) -> str:
    """Make a user query safe for FTS5.

    FTS5 has its own mini-language (AND/OR/NEAR/'') that surprises naive
    callers. We strip its punctuation and turn each word into a prefix
    match so 'Tokyo' matches 'tokyo trip 2024'.
    """
    safe = "".join(c if c.isalnum() or c.isspace() else " " for c in raw)
    parts = [p + "*" for p in safe.split() if len(p) >= 2]
    return " ".join(parts)


def find(*, query: str = "", kinds: list[str] | None = None,
         tags: str = "", date_after: str = "", date_before: str = "",
         limit: int = 20) -> dict:
    db = get_db()
    kinds_set = set(kinds or ["notes", "files"])
    tag_pat = f"%,{tags.strip()},%" if tags.strip() else None
    after_ts = _to_ts(date_after)
    before_ts = _to_ts(date_before)
    fts = _fts_query(query) if query else ""

    out: list[dict] = []

    if "notes" in kinds_set:
        out.extend(_search_notes(db, fts, tag_pat, after_ts, before_ts, limit))
    if "files" in kinds_set:
        out.extend(_search_files(db, fts, tag_pat, after_ts, before_ts, limit))

    # Stable ordering: best-ranked first across both kinds.
    out.sort(key=lambda r: r.get("rank", 0))
    return {"results": out[:limit], "query": query, "matched": len(out)}


def _search_notes(db, fts, tag_pat, after, before, limit) -> list[dict]:
    where, params = [], []
    if fts:
        where.append("notes.rowid IN (SELECT rowid FROM notes_fts WHERE notes_fts MATCH ?)")
        params.append(fts)
    if tag_pat:
        where.append("(',' || notes.tags || ',') LIKE ?")
        params.append(tag_pat)
    if after is not None:
        where.append("notes.updated_at >= ?")
        params.append(after)
    if before is not None:
        where.append("notes.updated_at < ?")
        params.append(before)
    sql_where = (" WHERE " + " AND ".join(where)) if where else ""
    rank_sql = "bm25(notes_fts)" if fts else "0"
    sql = (
        f"SELECT notes.id AS id, notes.title AS title, "
        f"  substr(notes.body, 1, 200) AS snippet, "
        f"  notes.tags AS tags, notes.updated_at AS updated_at, "
        f"  {rank_sql} AS rank, 'note' AS kind "
        f"FROM notes "
        + ("LEFT JOIN notes_fts ON notes_fts.rowid = notes.rowid " if fts else "")
        + sql_where
        + " ORDER BY rank, notes.updated_at DESC LIMIT ?"
    )
    params.append(limit)
    try:
        return db.fetchall(sql, params)
    except sqlite3.OperationalError:
        # FTS5 missing — caller can still page through via list_notes.
        return []


def _search_files(db, fts, tag_pat, after, before, limit) -> list[dict]:
    where, params = [], []
    if fts:
        where.append("files_meta.rowid IN (SELECT rowid FROM files_fts WHERE files_fts MATCH ?)")
        params.append(fts)
    if tag_pat:
        where.append("(',' || files_meta.tags || ',') LIKE ?")
        params.append(tag_pat)
    if after is not None:
        where.append("files_meta.created_at >= ?")
        params.append(after)
    if before is not None:
        where.append("files_meta.created_at < ?")
        params.append(before)
    sql_where = (" WHERE " + " AND ".join(where)) if where else ""
    rank_sql = "bm25(files_fts)" if fts else "0"
    sql = (
        f"SELECT files_meta.id AS id, files_meta.filename AS title, "
        f"  files_meta.description AS snippet, files_meta.tags AS tags, "
        f"  files_meta.created_at AS updated_at, "
        f"  {rank_sql} AS rank, 'file' AS kind "
        f"FROM files_meta "
        + ("LEFT JOIN files_fts ON files_fts.rowid = files_meta.rowid " if fts else "")
        + sql_where
        + " ORDER BY rank, files_meta.created_at DESC LIMIT ?"
    )
    params.append(limit)
    try:
        return db.fetchall(sql, params)
    except sqlite3.OperationalError:
        return []


def register(reg: ToolRegistry) -> None:
    reg.register(Tool(
        name="search.find",
        description=(
            "Find a specific note or file the user has stored. Use this "
            "(not notes.search / files.list) whenever the user asks "
            "'find / search / where is / show me X' — pass the parsed "
            "criteria, do not list everything and grep manually. Returns "
            "BM25-ranked results across notes + files."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query":       {"type": "string",  "description": "Free-text terms — proper nouns and IDs work well."},
                "kinds":       {"type": "array",   "items": {"type": "string", "enum": ["notes", "files"]},
                                "description": "Restrict to notes / files; default both."},
                "tags":        {"type": "string",  "description": "Single tag to filter by."},
                "date_after":  {"type": "string",  "description": "ISO date — only items updated/created on or after this."},
                "date_before": {"type": "string",  "description": "ISO date — only items before this."},
                "limit":       {"type": "integer", "default": 20, "description": "Max results across both kinds."},
            },
        },
        handler=find,
        category="search",
    ))
