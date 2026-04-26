"""REST + webhook endpoints for bots."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from ._deps import state

router = APIRouter(tags=["bots"], prefix="/bots")


class BotConfigIn(BaseModel):
    config: dict


# ---- catalog + instances ----

@router.get("/catalog")
def catalog(s=Depends(state)):
    return s.bots.list_kinds()


@router.get("")
def list_(s=Depends(state)):
    return s.bots.list_instances()


@router.get("/{bot_id}")
def get_one(bot_id: str, s=Depends(state)):
    insts = {b["id"]: b for b in s.bots.list_instances()}
    return insts.get(bot_id) or {"id": bot_id, "enabled": False, "status": "stopped", "config_set": False}


@router.put("/{bot_id}/config")
def save_config(bot_id: str, body: BotConfigIn, s=Depends(state)):
    try:
        s.bots.save_config(bot_id, body.config)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


@router.post("/{bot_id}/start")
def start(bot_id: str, s=Depends(state)):
    try:
        return s.bots.start(bot_id)
    except Exception as e:  # noqa: BLE001 — bots can fail any number of ways at startup
        raise HTTPException(400, f"{type(e).__name__}: {e}")


@router.post("/{bot_id}/stop")
def stop(bot_id: str, s=Depends(state)):
    s.bots.stop(bot_id)
    return {"ok": True}


# ---- webhook surface (公众号 / 企业微信) ----

@router.get("/wechat_oa/webhook", response_class=PlainTextResponse)
def wechat_oa_handshake(
    signature: str = Query(""),
    timestamp: str = Query(""),
    nonce: str = Query(""),
    echostr: str = Query(""),
    s=Depends(state),
):
    inst = s.bots.get_instance("wechat_oa")
    if not inst or not inst.verify_handshake(signature=signature, timestamp=timestamp, nonce=nonce):
        raise HTTPException(403, "invalid signature")
    return echostr


@router.post("/wechat_oa/webhook")
async def wechat_oa_message(request: Request, s=Depends(state)):
    inst = s.bots.get_instance("wechat_oa")
    if not inst:
        raise HTTPException(503, "bot not running")
    raw = await request.body()
    reply_xml = inst.handle_inbound(raw)
    return Response(reply_xml, media_type="application/xml")


@router.get("/wecom/webhook", response_class=PlainTextResponse)
def wecom_handshake(
    msg_signature: str = Query(""),
    timestamp: str = Query(""),
    nonce: str = Query(""),
    echostr: str = Query(""),
    s=Depends(state),
):
    inst = s.bots.get_instance("wecom")
    if not inst or not inst.verify_handshake(
        signature=msg_signature, timestamp=timestamp, nonce=nonce, echostr=echostr
    ):
        raise HTTPException(403, "invalid signature")
    return echostr


@router.post("/wecom/webhook")
async def wecom_message(request: Request, s=Depends(state)):
    inst = s.bots.get_instance("wecom")
    if not inst:
        raise HTTPException(503, "bot not running")
    raw = await request.body()
    reply_xml = inst.handle_inbound(raw)
    return Response(reply_xml, media_type="application/xml")
