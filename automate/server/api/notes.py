from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ... import notes as N
from ._deps import state

router = APIRouter(tags=["notes"], prefix="/notes")


class NoteIn(BaseModel):
    title: str = "Untitled"
    body: str = ""
    tags: str = ""
    pinned: bool = False


class NotePatch(BaseModel):
    title: str | None = None
    body: str | None = None
    tags: str | None = None
    pinned: bool | None = None


@router.get("")
def list_notes(s=Depends(state), query: str = "", tag: str = "", limit: int = 200):
    return N.list_notes(s.db, query=query, tag=tag, limit=limit)


@router.get("/tags")
def tags(s=Depends(state)):
    return N.all_tags(s.db)


@router.get("/{note_id}")
def read_note(note_id: str, s=Depends(state)):
    note = N.get_note(s.db, note_id)
    if not note:
        raise HTTPException(404)
    return note


@router.post("")
def create_note(body: NoteIn, s=Depends(state)):
    return N.create_note(s.db, title=body.title, body=body.body, tags=body.tags, pinned=body.pinned)


@router.patch("/{note_id}")
def patch_note(note_id: str, body: NotePatch, s=Depends(state)):
    note = N.update_note(s.db, note_id, title=body.title, body=body.body,
                         tags=body.tags, pinned=body.pinned)
    if not note:
        raise HTTPException(404)
    return note


@router.delete("/{note_id}")
def delete_note(note_id: str, s=Depends(state)):
    if not N.delete_note(s.db, note_id):
        raise HTTPException(404)
    return {"ok": True}
