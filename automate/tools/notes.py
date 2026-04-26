"""Tools that let any LLM read and write the user's notes."""
from __future__ import annotations

from .. import notes as N
from ..store import get_db
from .registry import Tool, ToolRegistry


def register(reg: ToolRegistry) -> None:
    reg.register(Tool(
        name="notes.create",
        description=(
            "Save a new note. Use this whenever the user shares something they'll "
            "want to find again — meeting takeaways, research, ideas, important info."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title":  {"type": "string"},
                "body":   {"type": "string", "default": ""},
                "tags":   {"type": "string", "description": "Comma-separated, e.g. 'work,project-x'"},
                "pinned": {"type": "boolean", "default": False},
            },
            "required": ["title"],
        },
        handler=lambda title, body="", tags="", pinned=False: N.create_note(
            get_db(), title=title, body=body, tags=tags, pinned=pinned),
        category="notes",
    ))

    reg.register(Tool(
        name="notes.search",
        description=(
            "Find notes the user has saved. Pass a query to search title+body, "
            "or a tag to filter, or both."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "default": ""},
                "tag":   {"type": "string", "default": ""},
                "limit": {"type": "integer", "default": 20},
            },
        },
        handler=lambda query="", tag="", limit=20: {
            "notes": [
                {"id": n["id"], "title": n["title"], "tags": n["tags"],
                 "snippet": n["body"][:200], "updated_at": n["updated_at"]}
                for n in N.list_notes(get_db(), query=query, tag=tag, limit=limit)
            ]
        },
        category="notes",
    ))

    reg.register(Tool(
        name="notes.read",
        description="Fetch the full content of a note by id.",
        parameters={
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        handler=lambda id: N.get_note(get_db(), id) or {"error": "not found"},
        category="notes",
    ))

    reg.register(Tool(
        name="notes.update",
        description="Edit an existing note. Pass only the fields you want to change.",
        parameters={
            "type": "object",
            "properties": {
                "id":     {"type": "string"},
                "title":  {"type": "string"},
                "body":   {"type": "string"},
                "tags":   {"type": "string"},
                "pinned": {"type": "boolean"},
            },
            "required": ["id"],
        },
        handler=lambda id, title=None, body=None, tags=None, pinned=None: (
            N.update_note(get_db(), id, title=title, body=body, tags=tags, pinned=pinned)
            or {"error": "not found"}
        ),
        category="notes",
    ))

    reg.register(Tool(
        name="notes.delete",
        description="Permanently delete a note.",
        parameters={
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        handler=lambda id: {"deleted": N.delete_note(get_db(), id)},
        category="notes",
        danger="medium",
    ))
