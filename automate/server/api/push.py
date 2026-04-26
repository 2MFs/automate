from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ... import push as P
from ._deps import state

router = APIRouter(tags=["push"], prefix="/push")


class SubscriptionIn(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


@router.get("/config")
def config(s=Depends(state)):
    keys = P.ensure_vapid(s.db)
    return {"vapid_public_key": keys["public"]}


@router.post("/subscribe")
def subscribe(body: SubscriptionIn, request: Request, s=Depends(state)):
    P.save_subscription(
        s.db,
        endpoint=body.endpoint, p256dh=body.p256dh, auth=body.auth,
        user_agent=request.headers.get("user-agent", ""),
    )
    return {"ok": True, "subscribers": len(P.list_subscriptions(s.db))}


@router.post("/test")
def test(s=Depends(state)):
    return P.push(s.db, title="autoMate", body="Push notifications are working ✓", url="/")
