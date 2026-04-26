"""Auth router — proxies to the cloud server's login endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ... import auth as A
from ._deps import state

router = APIRouter(tags=["auth"], prefix="/auth")


class LoginIn(BaseModel):
    email: str
    password: str


@router.get("/me")
def me(s=Depends(state)):
    return A.me(s.db)


@router.post("/login")
def login(body: LoginIn, s=Depends(state)):
    if not A.is_configured():
        raise HTTPException(503, "Cloud not configured (AUTOMATE_CLOUD_URL unset)")
    try:
        sess = A.login(s.db, email=body.email, password=body.password)
    except A.CloudUnavailable as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "email": sess.email, "tier": sess.tier}


@router.post("/logout")
def logout(s=Depends(state)):
    A.logout(s.db)
    return {"ok": True}
