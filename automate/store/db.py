"""SQLite storage with a tiny migration layer.

Tables:
- ``providers``    LLM provider configs (api_key encrypted)
- ``connections``  Tool/integration credentials (token encrypted, supports OAuth)
- ``settings``     Misc key/value (active provider, default model, ...)
- ``runs``         Agent run history (prompt → plan → tool calls → result)
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from ..settings import PATHS
from .crypto import Vault


_SCHEMA = """
CREATE TABLE IF NOT EXISTS providers (
  id            TEXT PRIMARY KEY,
  display_name  TEXT NOT NULL,
  base_url      TEXT,
  api_key_enc   TEXT,
  default_model TEXT,
  enabled       INTEGER NOT NULL DEFAULT 1,
  extra_json    TEXT NOT NULL DEFAULT '{}',
  updated_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS connections (
  id            TEXT PRIMARY KEY,
  display_name  TEXT NOT NULL,
  auth_kind     TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'disconnected',
  token_enc     TEXT,
  refresh_enc   TEXT,
  expires_at    REAL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  updated_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id          TEXT PRIMARY KEY,
  source      TEXT NOT NULL,
  prompt      TEXT NOT NULL,
  status      TEXT NOT NULL,
  trace_json  TEXT NOT NULL DEFAULT '[]',
  result      TEXT,
  started_at  REAL NOT NULL,
  ended_at    REAL
);

-- v5: personal infrastructure tables ----------------------------------------

CREATE TABLE IF NOT EXISTS notes (
  id           TEXT PRIMARY KEY,
  title        TEXT NOT NULL,
  body         TEXT NOT NULL DEFAULT '',
  tags         TEXT NOT NULL DEFAULT '',          -- comma-separated
  pinned       INTEGER NOT NULL DEFAULT 0,
  created_at   REAL NOT NULL,
  updated_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS notes_updated_idx ON notes(updated_at DESC);

CREATE TABLE IF NOT EXISTS files_meta (
  id           TEXT PRIMARY KEY,
  sha256       TEXT NOT NULL,
  filename     TEXT NOT NULL,
  mime         TEXT NOT NULL DEFAULT 'application/octet-stream',
  size         INTEGER NOT NULL,
  tags         TEXT NOT NULL DEFAULT '',
  description  TEXT NOT NULL DEFAULT '',
  created_at   REAL NOT NULL,
  -- v4.5.2: per-blob storage root so the user can change the file vault
  -- location without breaking access to previously-uploaded blobs. NULL
  -- means "use the default PATHS.files" (legacy rows from <=v4.5.1).
  storage_root TEXT
);
CREATE INDEX IF NOT EXISTS files_sha_idx     ON files_meta(sha256);
CREATE INDEX IF NOT EXISTS files_created_idx ON files_meta(created_at DESC);

CREATE TABLE IF NOT EXISTS reminders (
  id            TEXT PRIMARY KEY,
  body          TEXT NOT NULL,
  due_at        REAL NOT NULL,
  recurrence    TEXT,                              -- 'daily' | 'weekly' | NULL
  status        TEXT NOT NULL DEFAULT 'pending',   -- pending|fired|snoozed|dismissed
  fired_at      REAL,
  context_json  TEXT NOT NULL DEFAULT '{}',
  created_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS reminders_due_idx ON reminders(status, due_at);

CREATE TABLE IF NOT EXISTS memory (
  key         TEXT PRIMARY KEY,
  value       TEXT NOT NULL,
  updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
  endpoint    TEXT PRIMARY KEY,
  p256dh      TEXT NOT NULL,
  auth        TEXT NOT NULL,
  user_agent  TEXT NOT NULL DEFAULT '',
  created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS push_keys (
  id              INTEGER PRIMARY KEY CHECK (id = 1),
  vapid_private   TEXT NOT NULL,
  vapid_public    TEXT NOT NULL,
  vapid_subject   TEXT NOT NULL DEFAULT 'mailto:admin@automate.local'
);

-- v4.3: bot channels — Telegram / 微信公众号 / 企业微信 / 个人微信
CREATE TABLE IF NOT EXISTS bots (
  id              TEXT PRIMARY KEY,             -- bot kind: 'telegram', 'wechat_oa', 'wecom', 'wechat_personal'
  enabled         INTEGER NOT NULL DEFAULT 0,
  config_enc      TEXT NOT NULL DEFAULT '',     -- encrypted JSON blob: tokens, secrets, callback urls
  status          TEXT NOT NULL DEFAULT 'stopped',
  last_error      TEXT,
  updated_at      REAL NOT NULL
);

-- v4.4: hybrid retrieval — SQLite FTS5 mirrors of notes + files_meta.
-- Triggers below keep them in sync. The agent's `search.find` tool runs
-- BM25 ranking over these (Coze-style: keyword + structure beats pure
-- vector for proper-noun / id queries).
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
  title, body, tags,
  content='notes', content_rowid='rowid',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
  INSERT INTO notes_fts(rowid, title, body, tags) VALUES (new.rowid, new.title, new.body, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, title, body, tags) VALUES ('delete', old.rowid, old.title, old.body, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, title, body, tags) VALUES ('delete', old.rowid, old.title, old.body, old.tags);
  INSERT INTO notes_fts(rowid, title, body, tags) VALUES (new.rowid, new.title, new.body, new.tags);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
  filename, description, tags,
  content='files_meta', content_rowid='rowid',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files_meta BEGIN
  INSERT INTO files_fts(rowid, filename, description, tags) VALUES (new.rowid, new.filename, new.description, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files_meta BEGIN
  INSERT INTO files_fts(files_fts, rowid, filename, description, tags) VALUES ('delete', old.rowid, old.filename, old.description, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files_meta BEGIN
  INSERT INTO files_fts(files_fts, rowid, filename, description, tags) VALUES ('delete', old.rowid, old.filename, old.description, old.tags);
  INSERT INTO files_fts(rowid, filename, description, tags) VALUES (new.rowid, new.filename, new.description, new.tags);
END;
"""


class Database:
    def __init__(self, path: Path | None = None, vault: Vault | None = None):
        self.path = path or PATHS.db
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.executescript(_SCHEMA)
        self._migrate_v452()
        self._backfill_fts()
        self.vault = vault or Vault(PATHS.secret_key)

    def _migrate_v452(self) -> None:
        """v4.5.2: add files_meta.storage_root if upgrading from a db that
        predates the column. CREATE TABLE IF NOT EXISTS won't add a column
        to an existing table."""
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(files_meta)")}
        if "storage_root" not in cols:
            self._conn.execute("ALTER TABLE files_meta ADD COLUMN storage_root TEXT")

    def _backfill_fts(self) -> None:
        """One-shot: populate the FTS5 mirrors from existing rows on first
        upgrade. Triggers cover everything inserted *after* this point;
        rows that predate the v4.4 schema bump need a manual rebuild."""
        try:
            for table, fts in (("notes", "notes_fts"), ("files_meta", "files_fts")):
                row = self._conn.execute(f"SELECT count(*) FROM {fts}").fetchone()
                if row[0] > 0:
                    continue
                cols = "title, body, tags" if table == "notes" else "filename, description, tags"
                self._conn.execute(
                    f"INSERT INTO {fts}(rowid, {cols}) SELECT rowid, {cols} FROM {table}"
                )
        except sqlite3.OperationalError:
            # FTS5 not available in this SQLite build (very rare on
            # modern systems). Search just falls back to LIKE.
            pass

    # ---------- generic helpers ----------

    @contextmanager
    def cursor(self):
        cur = self._conn.cursor()
        try:
            yield cur
        finally:
            cur.close()

    def fetchone(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        with self.cursor() as cur:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
            return dict(row) if row else None

    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self.cursor() as cur:
            cur.execute(sql, tuple(params))

    # ---------- providers ----------

    def upsert_provider(self, *, id: str, display_name: str, base_url: str | None,
                        api_key: str | None, default_model: str | None,
                        enabled: bool = True, extra: dict | None = None) -> dict:
        api_key_enc = self.vault.encrypt(api_key) if api_key else ""
        self.execute(
            """INSERT INTO providers (id, display_name, base_url, api_key_enc, default_model, enabled, extra_json, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 display_name=excluded.display_name,
                 base_url=excluded.base_url,
                 api_key_enc=CASE WHEN excluded.api_key_enc='' THEN providers.api_key_enc ELSE excluded.api_key_enc END,
                 default_model=excluded.default_model,
                 enabled=excluded.enabled,
                 extra_json=excluded.extra_json,
                 updated_at=excluded.updated_at""",
            (id, display_name, base_url or "", api_key_enc, default_model or "",
             1 if enabled else 0, json.dumps(extra or {}), time.time()),
        )
        return self.get_provider(id)  # type: ignore[return-value]

    def get_provider(self, id: str, *, decrypt: bool = False) -> dict | None:
        row = self.fetchone("SELECT * FROM providers WHERE id = ?", (id,))
        if row and decrypt:
            row["api_key"] = self.vault.decrypt(row.pop("api_key_enc"))
        elif row:
            row["api_key_set"] = bool(row.pop("api_key_enc"))
        return row

    def list_providers(self) -> list[dict]:
        rows = self.fetchall("SELECT * FROM providers ORDER BY display_name")
        for r in rows:
            r["api_key_set"] = bool(r.pop("api_key_enc"))
        return rows

    def delete_provider(self, id: str) -> None:
        self.execute("DELETE FROM providers WHERE id = ?", (id,))

    # ---------- connections (tool integrations) ----------

    def upsert_connection(self, *, id: str, display_name: str, auth_kind: str,
                          status: str, token: str | None = None,
                          refresh: str | None = None, expires_at: float | None = None,
                          metadata: dict | None = None) -> dict:
        token_enc = self.vault.encrypt(token) if token else ""
        refresh_enc = self.vault.encrypt(refresh) if refresh else ""
        self.execute(
            """INSERT INTO connections (id, display_name, auth_kind, status, token_enc, refresh_enc, expires_at, metadata_json, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 display_name=excluded.display_name,
                 auth_kind=excluded.auth_kind,
                 status=excluded.status,
                 token_enc=CASE WHEN excluded.token_enc='' THEN connections.token_enc ELSE excluded.token_enc END,
                 refresh_enc=CASE WHEN excluded.refresh_enc='' THEN connections.refresh_enc ELSE excluded.refresh_enc END,
                 expires_at=excluded.expires_at,
                 metadata_json=excluded.metadata_json,
                 updated_at=excluded.updated_at""",
            (id, display_name, auth_kind, status, token_enc, refresh_enc,
             expires_at, json.dumps(metadata or {}), time.time()),
        )
        return self.get_connection(id)  # type: ignore[return-value]

    def get_connection(self, id: str, *, decrypt: bool = False) -> dict | None:
        row = self.fetchone("SELECT * FROM connections WHERE id = ?", (id,))
        if not row:
            return None
        if decrypt:
            row["token"] = self.vault.decrypt(row.pop("token_enc"))
            row["refresh"] = self.vault.decrypt(row.pop("refresh_enc"))
        else:
            row["token_set"] = bool(row.pop("token_enc"))
            row.pop("refresh_enc", None)
        return row

    def list_connections(self) -> list[dict]:
        rows = self.fetchall("SELECT * FROM connections ORDER BY display_name")
        for r in rows:
            r["token_set"] = bool(r.pop("token_enc"))
            r.pop("refresh_enc", None)
        return rows

    def delete_connection(self, id: str) -> None:
        self.execute("DELETE FROM connections WHERE id = ?", (id,))

    # ---------- settings (kv) ----------

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    # ---------- runs ----------

    def create_run(self, *, id: str, source: str, prompt: str) -> None:
        self.execute(
            "INSERT INTO runs (id, source, prompt, status, started_at) VALUES (?, ?, ?, 'running', ?)",
            (id, source, prompt, time.time()),
        )

    def append_trace(self, id: str, event: dict) -> None:
        row = self.fetchone("SELECT trace_json FROM runs WHERE id = ?", (id,))
        trace = json.loads(row["trace_json"]) if row else []
        trace.append(event)
        self.execute("UPDATE runs SET trace_json = ? WHERE id = ?", (json.dumps(trace), id))

    def finish_run(self, id: str, *, status: str, result: str | None) -> None:
        self.execute(
            "UPDATE runs SET status = ?, result = ?, ended_at = ? WHERE id = ?",
            (status, result, time.time(), id),
        )

    def list_runs(self, limit: int = 50) -> list[dict]:
        return self.fetchall("SELECT id, source, prompt, status, started_at, ended_at FROM runs ORDER BY started_at DESC LIMIT ?", (limit,))


_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        PATHS.ensure()
        _db = Database()
    return _db
