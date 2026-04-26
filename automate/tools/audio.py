"""audio.transcribe tool — paid tier.

This is the first tool flagged ``tier="pro"``. The agent loop's tier
check (loop.py) intercepts unauthenticated calls and asks the user to
sign in to autoMate Cloud. With a session, the call goes through and
hits whichever ASR provider is configured locally.
"""
from __future__ import annotations

from pathlib import Path

from .. import audio as A
from .. import files as F
from ..store import get_db
from .registry import Tool, ToolRegistry


def transcribe(file_id: str, provider: str = "", language: str = "",
               save_as_note: bool = True) -> dict:
    db = get_db()
    meta = F.get_meta(db, file_id)
    if not meta:
        return {"error": f"file not found: {file_id}"}
    path = F.open_blob(meta)
    if not path.exists():
        return {"error": "blob missing on disk"}
    try:
        result = A.transcribe(audio_path=Path(path), db=db, provider=provider, language=language)
    except RuntimeError as e:
        return {"error": str(e)}
    if save_as_note:
        from .. import notes as N
        note = N.create_note(
            db,
            title=f"Transcript: {meta['filename']}",
            body=result["text"],
            tags="transcript,audio",
        )
        result["note_id"] = note["id"]
    return result


def register(reg: ToolRegistry) -> None:
    reg.register(Tool(
        name="audio.transcribe",
        description=(
            "Transcribe a previously-uploaded audio file (WAV / MP3 / "
            "M4A / OGG). Custom vocabulary mined from the user's notes "
            "biases proper-noun accuracy. Optionally saves the "
            "transcript as a note tagged 'transcript,audio'. "
            "REQUIRES Pro subscription."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_id":      {"type": "string",  "description": "ID returned by files.upload."},
                "provider":     {"type": "string",  "description": "'tencent_asr' (best Chinese) or 'openai_whisper'. Default: auto."},
                "language":     {"type": "string",  "description": "BCP-47 hint, e.g. 'zh', 'en'. Default auto."},
                "save_as_note": {"type": "boolean", "default": True},
            },
            "required": ["file_id"],
        },
        handler=transcribe,
        category="audio",
        tier="pro",
    ))
