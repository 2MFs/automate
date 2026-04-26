"""Audio recording API — upload + transcribe in one shot.

The frontend's record button (MediaRecorder) hits POST /api/audio/record
with a single Blob (the whole recording, not chunked — phone meetings
fit in a single multipart upload up to ~50MB which is plenty).

Server saves the file via the existing files store (so the user can
play it back from the Files tab), then runs transcription synchronously
and returns the transcript. If a Pro session is missing, returns 402
with a clean error the SPA can display.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ... import audio as A
from ... import auth, files as F, notes as N
from ._deps import state

router = APIRouter(tags=["audio"], prefix="/audio")


@router.post("/record")
async def record(
    s=Depends(state),
    file: UploadFile = File(...),
    language: str = Form(""),
    provider: str = Form(""),
    save_as_note: bool = Form(True),
):
    if not auth.get_session(s.db):
        raise HTTPException(
            402, "Audio transcription requires a Pro subscription. "
            "Sign in via Settings → autoMate Cloud."
        )
    blob = await file.read()
    meta = F.store_blob(
        blob, filename=file.filename or "recording.webm",
        mime=file.content_type or "audio/webm",
        tags="audio,recording", description="Voice recording",
        db=s.db,
    )
    try:
        result = A.transcribe(
            audio_path=F.open_blob(meta), db=s.db,
            provider=provider, language=language,
        )
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    if save_as_note:
        note = N.create_note(
            s.db,
            title=f"Recording {meta['filename']}",
            body=result["text"],
            tags="transcript,audio",
        )
        result["note_id"] = note["id"]
    result["file_id"] = meta["id"]
    return result


@router.get("/providers")
def providers(s=Depends(state)):
    """What's available for transcription on this device."""
    selected = A.pick_provider(s.db)
    return {
        "active": selected.id if selected else None,
        "active_label": selected.label if selected else None,
        "configured": selected is not None,
    }
