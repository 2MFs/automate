from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ... import files as F
from ._deps import state

router = APIRouter(tags=["files"], prefix="/files")


@router.get("")
def list_files(s=Depends(state), query: str = "", tag: str = "", limit: int = 200):
    return F.list_files(s.db, query=query, tag=tag, limit=limit)


@router.get("/usage")
def usage(s=Depends(state)):
    return {"total_bytes": F.total_size(s.db), "count": len(F.list_files(s.db, limit=10_000))}


@router.post("")
async def upload(
    s=Depends(state),
    file: UploadFile = File(...),
    tags: str = Form(""),
    description: str = Form(""),
):
    content = await file.read()
    return F.store_blob(
        content, filename=file.filename or "upload",
        mime=file.content_type, tags=tags, description=description, db=s.db,
    )


@router.get("/{file_id}")
def get_meta(file_id: str, s=Depends(state)):
    meta = F.get_meta(s.db, file_id)
    if not meta:
        raise HTTPException(404)
    return meta


@router.get("/{file_id}/raw")
def get_raw(file_id: str, s=Depends(state)):
    meta = F.get_meta(s.db, file_id)
    if not meta:
        raise HTTPException(404)
    path = F.open_blob(meta)
    if not path.exists():
        raise HTTPException(410, "blob missing")
    return FileResponse(path, media_type=meta["mime"], filename=meta["filename"])


@router.delete("/{file_id}")
def delete(file_id: str, s=Depends(state)):
    if not F.delete_file(s.db, file_id):
        raise HTTPException(404)
    return {"ok": True}
