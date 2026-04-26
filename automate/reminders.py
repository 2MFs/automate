"""Reminders — the only proactive surface autoMate has.

A background thread polls the DB once a minute. When a reminder's ``due_at``
has passed and its status is still ``pending``, we mark it ``fired`` and
fan out a Web Push to every subscribed client (typically the user's PWA on
their phone). Recurring reminders are then re-scheduled.

Reminders are also surfaced as tools so any LLM can create them on the
user's behalf ("remind me at 9am to call mom").
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from . import push
from .store import Database

log = logging.getLogger("automate.reminders")


# ---------- CRUD ----------

def create(db: Database, *, body: str, due_at: float, recurrence: str | None = None,
           context: dict | None = None) -> dict:
    rid = uuid.uuid4().hex
    db.execute(
        "INSERT INTO reminders (id, body, due_at, recurrence, status, context_json, created_at) "
        "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
        (rid, body, float(due_at), recurrence, json.dumps(context or {}), time.time()),
    )
    return get(db, rid)  # type: ignore[return-value]


def get(db: Database, reminder_id: str) -> dict | None:
    return db.fetchone("SELECT * FROM reminders WHERE id = ?", (reminder_id,))


def list_all(db: Database, *, status: str | None = None, limit: int = 200) -> list[dict]:
    if status:
        return db.fetchall(
            "SELECT * FROM reminders WHERE status = ? ORDER BY due_at ASC LIMIT ?",
            (status, limit),
        )
    return db.fetchall(
        "SELECT * FROM reminders ORDER BY due_at ASC LIMIT ?",
        (limit,),
    )


def snooze(db: Database, reminder_id: str, *, minutes: int) -> dict | None:
    r = get(db, reminder_id)
    if not r:
        return None
    new_due = max(time.time(), r["due_at"]) + minutes * 60
    db.execute("UPDATE reminders SET due_at = ?, status = 'pending', fired_at = NULL WHERE id = ?",
               (new_due, reminder_id))
    return get(db, reminder_id)


def dismiss(db: Database, reminder_id: str) -> bool:
    if not get(db, reminder_id):
        return False
    db.execute("UPDATE reminders SET status = 'dismissed' WHERE id = ?", (reminder_id,))
    return True


def delete(db: Database, reminder_id: str) -> bool:
    if not get(db, reminder_id):
        return False
    db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    return True


# ---------- scheduler ----------

_RECUR_DELTA = {
    "minutely": timedelta(minutes=1),
    "hourly":   timedelta(hours=1),
    "daily":    timedelta(days=1),
    "weekly":   timedelta(weeks=1),
}


class Scheduler:
    """Background thread that fires due reminders."""

    def __init__(self, db: Database, *, poll_seconds: float = 30.0):
        self.db = db
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="automate-reminders")
        self._thread.start()
        log.info("reminder scheduler started")

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001
                log.exception("scheduler tick failed: %s", e)

    def tick(self) -> int:
        now = time.time()
        due = self.db.fetchall(
            "SELECT * FROM reminders WHERE status = 'pending' AND due_at <= ?",
            (now,),
        )
        for r in due:
            self._fire(r, now)
        return len(due)

    def _fire(self, reminder: dict, now: float) -> None:
        log.info("firing reminder %s: %s", reminder["id"], reminder["body"][:60])
        self.db.execute(
            "UPDATE reminders SET status = 'fired', fired_at = ? WHERE id = ?",
            (now, reminder["id"]),
        )
        try:
            push.push(
                self.db,
                title="autoMate reminder",
                body=reminder["body"],
                url=f"/?reminder={reminder['id']}",
                tag=f"reminder-{reminder['id']}",
            )
        except Exception as e:  # noqa: BLE001
            log.warning("push fanout failed for %s: %s", reminder["id"], e)
        # Re-schedule recurring reminders.
        rec = reminder.get("recurrence")
        delta = _RECUR_DELTA.get(rec or "")
        if delta:
            next_due = (datetime.fromtimestamp(reminder["due_at"]) + delta).timestamp()
            self.db.execute(
                "INSERT INTO reminders (id, body, due_at, recurrence, status, context_json, created_at) "
                "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (uuid.uuid4().hex, reminder["body"], next_due, rec,
                 reminder.get("context_json") or "{}", time.time()),
            )
