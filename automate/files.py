"""Personal file vault — content-addressed local storage.

Files are stored once, keyed by SHA-256 (so duplicate uploads cost zero
extra space). Metadata in SQLite. Any AI can pull a file's bytes via
``GET /api/files/<id>/raw`` and offload it to its own context, or stash
something for the user to retrieve later.

Future: a relay can sync file metadata + sign URLs so a phone can fetch
content directly from the laptop without extra hops.
"""
from __future__ import annotations

import hashlib
import mimetypes
import time
import uuid
from pathlib import Path

from .settings import PATHS
from .store import Database


def store_blob(content: bytes, *, filename: str, mime: str | None = None,
               tags: str = "", description: str = "", db: Database) -> dict:
    PATHS.ensure()
    sha = hashlib.sha256(content).hexdigest()
    blob_path = PATHS.files / sha
    if not blob_path.exists():
        blob_path.write_bytes(content)
    fid = uuid.uuid4().hex
    db.execute(
        "INSERT INTO files_meta (id, sha256, filename, mime, size, tags, description, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            fid, sha, filename,
            mime or mimetypes.guess_type(filename)[0] or "application/octet-stream",
            len(content),
            _norm_tags(tags), description, time.time(),
        ),
    )
    return get_meta(db, fid)  # type: ignore[return-value]


def get_meta(db: Database, file_id: str) -> dict | None:
    return db.fetchone("SELECT * FROM files_meta WHERE id = ?", (file_id,))


def open_blob(meta: dict) -> Path:
    return PATHS.files / meta["sha256"]


def list_files(db: Database, *, query: str = "", tag: str = "", limit: int = 200) -> list[dict]:
    where, params = ["1=1"], []
    if query:
        where.append("(filename LIKE ? OR description LIKE ?)")
        like = f"%{query}%"
        params += [like, like]
    if tag:
        where.append("(',' || tags || ',') LIKE ?")
        params.append(f"%,{tag.strip()},%")
    sql = f"SELECT * FROM files_meta WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return db.fetchall(sql, tuple(params))


def delete_file(db: Database, file_id: str) -> bool:
    meta = get_meta(db, file_id)
    if not meta:
        return False
    db.execute("DELETE FROM files_meta WHERE id = ?", (file_id,))
    # Garbage-collect the blob if no other meta row references this sha.
    leftover = db.fetchone("SELECT 1 FROM files_meta WHERE sha256 = ? LIMIT 1", (meta["sha256"],))
    if not leftover:
        try:
            (PATHS.files / meta["sha256"]).unlink()
        except FileNotFoundError:
            pass
    return True


def total_size(db: Database) -> int:
    row = db.fetchone("SELECT COALESCE(SUM(size), 0) AS total FROM files_meta")
    return int(row["total"]) if row else 0


def _norm_tags(raw: str) -> str:
    return ",".join(sorted({t.strip() for t in (raw or "").split(",") if t.strip()}))
