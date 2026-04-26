"""Long-term key-value memory.

Cross-session, cross-AI scratchpad. Differs from notes:

- Notes are documents — titles, bodies, you can browse them.
- Memory is structured facts — "user.preferred_language=zh", "trip.dest=Tokyo".

Any AI can write/read so context survives a fresh chat with a different model.
"""
from __future__ import annotations

import time

from .store import Database


def set_value(db: Database, key: str, value: str) -> None:
    db.execute(
        "INSERT INTO memory (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value, time.time()),
    )


def get_value(db: Database, key: str) -> str | None:
    row = db.fetchone("SELECT value FROM memory WHERE key = ?", (key,))
    return row["value"] if row else None


def list_all(db: Database, *, prefix: str = "") -> list[dict]:
    if prefix:
        return db.fetchall(
            "SELECT * FROM memory WHERE key LIKE ? ORDER BY key",
            (prefix + "%",),
        )
    return db.fetchall("SELECT * FROM memory ORDER BY key")


def delete(db: Database, key: str) -> bool:
    if not get_value(db, key):
        return False
    db.execute("DELETE FROM memory WHERE key = ?", (key,))
    return True
