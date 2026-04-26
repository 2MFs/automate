"""Channels API — single inbox endpoint that an external IM gateway
(OpenClaw, custom script, n8n, ...) calls to deliver messages to the
agent. See ``automate/channels.py`` for the architectural rationale.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from ... import channels as C
from ._deps import state

router = APIRouter(tags=["channels"], prefix="/channels")


class InboundIn(BaseModel):
    channel: str
    user_id: str
    text: str
    context: dict | None = None


def _check_token(authorization: str | None, db) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing Bearer token")
    if not C.verify_token(db, authorization.split(" ", 1)[1].strip()):
        raise HTTPException(401, "invalid bridge token")


@router.post("/inbox")
def inbox(body: InboundIn,
          s=Depends(state),
          authorization: str | None = Header(None)):
    _check_token(authorization, s.db)
    if not body.text.strip():
        raise HTTPException(400, "text is empty")
    msg = C.InboundMessage(
        channel=body.channel.strip() or "unknown",
        user_id=body.user_id.strip() or "anonymous",
        text=body.text,
        context=body.context or {},
    )
    try:
        reply = C.process_inbound(msg, agent=s.agent)
    except Exception as e:  # noqa: BLE001 — surface to the gateway, don't 500
        # Most common: no LLM provider configured. Tell the gateway so
        # it can render a useful "set me up" reply to the user.
        raise HTTPException(503, f"agent error: {type(e).__name__}: {e}")
    return {"text": reply.text, "run_id": reply.run_id, "ms": reply.ms}


@router.get("/bridge")
def bridge_info(s=Depends(state)):
    """Read the bridge URL + token so the user can paste them into
    OpenClaw (or whichever gateway they're using)."""
    return {
        "inbox_url_path": "/api/channels/inbox",
        "token": C.get_or_create_token(s.db),
        "docs_path": "/help#channels",
    }


@router.post("/bridge/regenerate")
def regenerate(s=Depends(state)):
    return {"token": C.regenerate_token(s.db)}
