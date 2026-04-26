"""Tools that let any LLM set / list / snooze / dismiss reminders."""
from __future__ import annotations

import time
from datetime import datetime

from .. import reminders as R
from ..store import get_db
from .registry import Tool, ToolRegistry


def _parse_when(when: str) -> float:
    """Accept ISO 8601 ('2026-04-26T09:00') or a relative offset ('+30m','+2h','+1d').

    Naive parser — good enough for an LLM hand-off; structured input wins.
    """
    when = (when or "").strip()
    if when.startswith("+"):
        unit = when[-1].lower()
        n = int(when[1:-1])
        seconds = n * {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit, 60)
        return time.time() + seconds
    # ISO fallback
    try:
        if "T" not in when and " " not in when:
            when = when + "T00:00"
        return datetime.fromisoformat(when).timestamp()
    except ValueError as e:
        raise ValueError(f"can't parse 'when': {when!r} — use ISO datetime or +Nm/+Nh/+Nd") from e


def register(reg: ToolRegistry) -> None:
    reg.register(Tool(
        name="reminders.create",
        description=(
            "Schedule a reminder. The user gets a push notification on their phone "
            "when it fires (if a PWA is installed). 'when' accepts ISO datetime "
            "('2026-04-26T09:00') or a relative offset ('+30m', '+2h', '+1d')."
        ),
        parameters={
            "type": "object",
            "properties": {
                "body":       {"type": "string", "description": "What to remind the user about."},
                "when":       {"type": "string", "description": "ISO datetime or +30m / +2h / +1d"},
                "recurrence": {"type": "string", "enum": ["", "hourly", "daily", "weekly"], "default": ""},
            },
            "required": ["body", "when"],
        },
        handler=lambda body, when, recurrence="": R.create(
            get_db(), body=body, due_at=_parse_when(when),
            recurrence=recurrence or None),
        category="reminders",
    ))

    reg.register(Tool(
        name="reminders.list",
        description="List reminders, optionally filtered by status.",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["", "pending", "fired", "snoozed", "dismissed"], "default": ""},
                "limit":  {"type": "integer", "default": 50},
            },
        },
        handler=lambda status="", limit=50: {
            "reminders": R.list_all(get_db(), status=status or None, limit=limit)
        },
        category="reminders",
    ))

    reg.register(Tool(
        name="reminders.snooze",
        description="Snooze a reminder for N minutes (re-fires later).",
        parameters={
            "type": "object",
            "properties": {
                "id":      {"type": "string"},
                "minutes": {"type": "integer", "default": 10},
            },
            "required": ["id"],
        },
        handler=lambda id, minutes=10: R.snooze(get_db(), id, minutes=minutes) or {"error": "not found"},
        category="reminders",
    ))

    reg.register(Tool(
        name="reminders.dismiss",
        description="Mark a reminder dismissed (won't re-fire).",
        parameters={
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        handler=lambda id: {"dismissed": R.dismiss(get_db(), id)},
        category="reminders",
    ))
