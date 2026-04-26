"""Tools that let any LLM read/write the user's long-term key-value memory."""
from __future__ import annotations

from .. import memory as M
from ..store import get_db
from .registry import Tool, ToolRegistry


def register(reg: ToolRegistry) -> None:
    reg.register(Tool(
        name="memory.set",
        description=(
            "Store a fact for future sessions. Use dotted keys like "
            "'user.preferred_language' or 'project.alpha.repo'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "key":   {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        },
        handler=lambda key, value: (M.set_value(get_db(), key, value), {"ok": True})[1],
        category="memory",
    ))

    reg.register(Tool(
        name="memory.get",
        description="Retrieve a previously-stored fact by key.",
        parameters={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
        handler=lambda key: {"value": M.get_value(get_db(), key)},
        category="memory",
    ))

    reg.register(Tool(
        name="memory.list",
        description="List all stored facts. Pass a prefix to filter.",
        parameters={
            "type": "object",
            "properties": {"prefix": {"type": "string", "default": ""}},
        },
        handler=lambda prefix="": {"items": M.list_all(get_db(), prefix=prefix)},
        category="memory",
    ))

    reg.register(Tool(
        name="memory.delete",
        description="Forget a fact.",
        parameters={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
        handler=lambda key: {"deleted": M.delete(get_db(), key)},
        category="memory",
        danger="medium",
    ))
