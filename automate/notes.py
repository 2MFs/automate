"""Personal notes — Markdown documents stored in SQLite.

The point of notes in autoMate is *not* to be a Notion clone. The point is
that any AI you're using (Kimi, Claude, GPT, …) can write into your notes
via tools, and any AI can read them back later as context. Your memory
travels with you, not with whichever chat UI you happened to open today.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from .store import Database


def create_note(db: Database, *, title: str, body: str = "", tags: str = "",
                pinned: bool = False) -> dict:
    nid = uuid.uuid4().hex
    now = time.time()
    db.execute(
        "INSERT INTO notes (id, title, body, tags, pinned, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (nid, title.strip() or "Untitled", body, _norm_tags(tags),
         1 if pinned else 0, now, now),
    )
    return get_note(db, nid)  # type: ignore[return-value]


def update_note(db: Database, note_id: str, *, title: str | None = None,
                body: str | None = None, tags: str | None = None,
                pinned: bool | None = None) -> dict | None:
    existing = get_note(db, note_id)
    if not existing:
        return None
    db.execute(
        "UPDATE notes SET title=?, body=?, tags=?, pinned=?, updated_at=? WHERE id=?",
        (
            title if title is not None else existing["title"],
            body if body is not None else existing["body"],
            _norm_tags(tags) if tags is not None else existing["tags"],
            (1 if pinned else 0) if pinned is not None else existing["pinned"],
            time.time(),
            note_id,
        ),
    )
    return get_note(db, note_id)


def get_note(db: Database, note_id: str) -> dict | None:
    return db.fetchone("SELECT * FROM notes WHERE id = ?", (note_id,))


def list_notes(db: Database, *, query: str = "", tag: str = "",
               limit: int = 200) -> list[dict]:
    """List notes, optionally filtered by query / tag.

    When ``query`` is given, we use SQLite FTS5 (BM25) for ranking — this
    is the Coze-style retrieval path. Each whitespace-separated word
    becomes a prefix match, so 'tokyo' finds 'Tokyo Trip 2024'. If FTS5
    isn't compiled into the host's SQLite (rare on modern systems), we
    fall back to LIKE so the UI still works.
    """
    where, params = ["1=1"], []
    if query:
        fts = _fts_query(query)
        if fts:
            try:
                # Probe FTS5 with a cheap query. If it works, route through it.
                db.fetchone("SELECT 1 FROM notes_fts LIMIT 1")
                where.append(
                    "rowid IN (SELECT rowid FROM notes_fts WHERE notes_fts MATCH ?)"
                )
                params.append(fts)
            except Exception:  # noqa: BLE001
                where.append("(title LIKE ? OR body LIKE ?)")
                like = f"%{query}%"
                params += [like, like]
        else:
            where.append("(title LIKE ? OR body LIKE ?)")
            like = f"%{query}%"
            params += [like, like]
    if tag:
        where.append("(',' || tags || ',') LIKE ?")
        params.append(f"%,{tag.strip()},%")
    sql = (
        f"SELECT * FROM notes WHERE {' AND '.join(where)} "
        f"ORDER BY pinned DESC, updated_at DESC LIMIT ?"
    )
    params.append(limit)
    return db.fetchall(sql, tuple(params))


def _fts_query(raw: str) -> str:
    """Sanitise user input for FTS5 (strip operators, prefix-match each word)."""
    safe = "".join(c if c.isalnum() or c.isspace() else " " for c in raw)
    parts = [p + "*" for p in safe.split() if len(p) >= 2]
    return " ".join(parts)


def delete_note(db: Database, note_id: str) -> bool:
    if not get_note(db, note_id):
        return False
    db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    return True


def all_tags(db: Database) -> list[str]:
    rows = db.fetchall("SELECT DISTINCT tags FROM notes WHERE tags != ''")
    out: set[str] = set()
    for r in rows:
        for t in r["tags"].split(","):
            t = t.strip()
            if t:
                out.add(t)
    return sorted(out)


def _norm_tags(raw: str) -> str:
    return ",".join(sorted({t.strip() for t in (raw or "").split(",") if t.strip()}))
