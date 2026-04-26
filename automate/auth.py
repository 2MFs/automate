"""Cloud-account auth client — the open-source half of the SiYuan-style
moat.

Architecture (from the v4.4 plan):

   Open-source client (this file)
       ↕ HTTPS
   Closed-source cloud server (separate `automate-cloud` repo)
       ├─ account registration
       ├─ paid tier billing
       └─ relay of paid features (transcription, public-content
          extraction, cloud storage)

This module just speaks to whatever URL the user has set as
``AUTOMATE_CLOUD_URL``. When that env var is empty (today), we degrade
gracefully: the UI shows "Cloud sync coming soon" and pro-tier tools
return ``needs_pro_subscription`` to the agent.

Tokens are stored in the existing ``connections`` table under id
``automate_cloud`` and Fernet-encrypted via the ``Vault``. No plaintext
secrets touch disk.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .store import Database, get_db

CONNECTION_ID = "automate_cloud"


@dataclass
class Session:
    token: str
    email: str
    tier: str           # 'free' | 'pro'
    expires_at: float | None = None


def cloud_url() -> str:
    """Return the configured cloud base URL, or '' if not set yet."""
    return (os.environ.get("AUTOMATE_CLOUD_URL") or "").rstrip("/")


def is_configured() -> bool:
    return bool(cloud_url())


# ---------- session storage ----------

def get_session(db: Database | None = None) -> Session | None:
    db = db or get_db()
    row = db.get_connection(CONNECTION_ID, decrypt=True)
    if not row or not row.get("token"):
        return None
    if row.get("expires_at") and time.time() > float(row["expires_at"]):
        return None
    metadata = json.loads(row.get("metadata_json") or "{}")
    return Session(
        token=row["token"],
        email=metadata.get("email", ""),
        tier=metadata.get("tier", "free"),
        expires_at=row.get("expires_at"),
    )


def store_session(db: Database, *, token: str, email: str, tier: str,
                  expires_at: float | None = None) -> Session:
    db.upsert_connection(
        id=CONNECTION_ID,
        display_name="autoMate Cloud",
        auth_kind="bearer",
        status="connected",
        token=token,
        expires_at=expires_at,
        metadata={"email": email, "tier": tier},
    )
    return Session(token=token, email=email, tier=tier, expires_at=expires_at)


def clear_session(db: Database) -> None:
    db.delete_connection(CONNECTION_ID)


# ---------- HTTPS calls to the cloud ----------

class CloudUnavailable(Exception):
    """Raised when AUTOMATE_CLOUD_URL is unset or unreachable."""


def _http(method: str, path: str, *, body: dict | None = None,
          token: str | None = None, timeout: int = 15) -> dict:
    base = cloud_url()
    if not base:
        raise CloudUnavailable("AUTOMATE_CLOUD_URL not configured")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            payload = {"error": str(e)}
        raise CloudUnavailable(payload.get("error") or f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise CloudUnavailable(f"unreachable: {e.reason}") from e


def login(db: Database, *, email: str, password: str) -> Session:
    payload = _http("POST", "/api/auth/login", body={"email": email, "password": password})
    return store_session(
        db,
        token=payload["token"],
        email=email,
        tier=payload.get("tier", "free"),
        expires_at=payload.get("expires_at"),
    )


def logout(db: Database) -> None:
    sess = get_session(db)
    if sess:
        try:
            _http("POST", "/api/auth/logout", token=sess.token, timeout=5)
        except CloudUnavailable:
            pass    # best-effort; clear local regardless
    clear_session(db)


def me(db: Database) -> dict:
    sess = get_session(db)
    if not sess:
        return {"logged_in": False, "cloud_configured": is_configured()}
    return {
        "logged_in": True,
        "email": sess.email,
        "tier": sess.tier,
        "cloud_configured": True,
    }
