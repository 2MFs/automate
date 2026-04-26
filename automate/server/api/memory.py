from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ... import memory as M
from ._deps import state

router = APIRouter(tags=["memory"], prefix="/memory")


class KV(BaseModel):
    key: str
    value: str


@router.get("")
def list_(s=Depends(state), prefix: str = ""):
    return M.list_all(s.db, prefix=prefix)


@router.put("")
def put(body: KV, s=Depends(state)):
    M.set_value(s.db, body.key, body.value)
    return {"ok": True}


@router.delete("/{key:path}")
def delete(key: str, s=Depends(state)):
    if not M.delete(s.db, key):
        raise HTTPException(404)
    return {"ok": True}
