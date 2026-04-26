from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ... import reminders as R
from ._deps import state

router = APIRouter(tags=["reminders"], prefix="/reminders")


class ReminderIn(BaseModel):
    body: str
    due_at: float                 # unix seconds
    recurrence: str | None = None


@router.get("")
def list_(s=Depends(state), status: str = "", limit: int = 200):
    return R.list_all(s.db, status=status or None, limit=limit)


@router.post("")
def create(body: ReminderIn, s=Depends(state)):
    return R.create(s.db, body=body.body, due_at=body.due_at, recurrence=body.recurrence)


@router.post("/{rid}/snooze")
def snooze(rid: str, minutes: int = 10, s=Depends(state)):
    out = R.snooze(s.db, rid, minutes=minutes)
    if not out:
        raise HTTPException(404)
    return out


@router.post("/{rid}/dismiss")
def dismiss(rid: str, s=Depends(state)):
    if not R.dismiss(s.db, rid):
        raise HTTPException(404)
    return {"ok": True}


@router.delete("/{rid}")
def delete(rid: str, s=Depends(state)):
    if not R.delete(s.db, rid):
        raise HTTPException(404)
    return {"ok": True}
