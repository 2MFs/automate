"""Tools that let any LLM put / list / get files in the user's vault."""
from __future__ import annotations

import base64

from .. import files as F
from ..store import get_db
from .registry import Tool, ToolRegistry


def register(reg: ToolRegistry) -> None:
    reg.register(Tool(
        name="files.put",
        description=(
            "Store a file in the user's vault. Pass content as base64 (small files only — "
            "for big uploads use the HTTP endpoint POST /api/files)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "filename":    {"type": "string"},
                "content_b64": {"type": "string"},
                "mime":        {"type": "string"},
                "tags":        {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["filename", "content_b64"],
        },
        handler=lambda filename, content_b64, mime=None, tags="", description="": F.store_blob(
            base64.b64decode(content_b64),
            filename=filename, mime=mime, tags=tags, description=description, db=get_db(),
        ),
        category="files",
        danger="low",
    ))

    reg.register(Tool(
        name="files.list",
        description="List files in the user's vault, optionally filtered by query/tag.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "default": ""},
                "tag":   {"type": "string", "default": ""},
                "limit": {"type": "integer", "default": 50},
            },
        },
        handler=lambda query="", tag="", limit=50: {
            "files": [
                {"id": f["id"], "filename": f["filename"], "mime": f["mime"],
                 "size": f["size"], "tags": f["tags"], "description": f["description"]}
                for f in F.list_files(get_db(), query=query, tag=tag, limit=limit)
            ]
        },
        category="files",
    ))

    reg.register(Tool(
        name="files.read",
        description=(
            "Read a stored file's bytes (returned as base64). Don't use for "
            "large media — call /api/files/<id>/raw directly instead."
        ),
        parameters={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "max_bytes": {"type": "integer", "default": 1048576},
            },
            "required": ["id"],
        },
        handler=lambda id, max_bytes=1048576: _read_blob(id, max_bytes),
        category="files",
    ))

    reg.register(Tool(
        name="files.delete",
        description="Delete a file from the vault.",
        parameters={
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        handler=lambda id: {"deleted": F.delete_file(get_db(), id)},
        category="files",
        danger="medium",
    ))


def _read_blob(file_id: str, max_bytes: int) -> dict:
    db = get_db()
    meta = F.get_meta(db, file_id)
    if not meta:
        return {"error": "not found"}
    path = F.open_blob(meta)
    if not path.exists():
        return {"error": "blob missing on disk"}
    data = path.read_bytes()[:max_bytes]
    return {
        "id": meta["id"],
        "filename": meta["filename"],
        "mime": meta["mime"],
        "size": meta["size"],
        "truncated": len(data) < meta["size"],
        "content_b64": base64.b64encode(data).decode(),
    }
