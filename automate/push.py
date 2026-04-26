"""Web Push (VAPID) — proactive notifications to the user's PWA.

Generates a VAPID keypair on first run and stashes it in the DB so the
public key survives restarts. Uses ``pywebpush`` if installed; if not, the
push functions degrade to no-ops (the rest of autoMate keeps working).
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Iterable

from .store import Database

log = logging.getLogger("automate.push")


def ensure_vapid(db: Database) -> dict:
    """Return {public, private, subject}, generating on first call."""
    row = db.fetchone("SELECT * FROM push_keys WHERE id = 1")
    if row:
        return {"public": row["vapid_public"], "private": row["vapid_private"],
                "subject": row["vapid_subject"]}
    pub_b64, priv_b64 = _generate_vapid()
    db.execute(
        "INSERT INTO push_keys (id, vapid_private, vapid_public, vapid_subject) VALUES (1, ?, ?, ?)",
        (priv_b64, pub_b64, "mailto:admin@automate.local"),
    )
    return {"public": pub_b64, "private": priv_b64, "subject": "mailto:admin@automate.local"}


def _generate_vapid() -> tuple[str, str]:
    """Return (public_b64url, private_b64url) using cryptography (already a dep)."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    priv = ec.generate_private_key(ec.SECP256R1())
    priv_bytes = priv.private_numbers().private_value.to_bytes(32, "big")
    pub_numbers = priv.public_key().public_numbers()
    raw_pub = b"\x04" + pub_numbers.x.to_bytes(32, "big") + pub_numbers.y.to_bytes(32, "big")
    return _b64url(raw_pub), _b64url(priv_bytes)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def save_subscription(db: Database, *, endpoint: str, p256dh: str, auth: str,
                      user_agent: str = "") -> None:
    import time
    db.execute(
        "INSERT OR REPLACE INTO push_subscriptions (endpoint, p256dh, auth, user_agent, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (endpoint, p256dh, auth, user_agent, time.time()),
    )


def list_subscriptions(db: Database) -> list[dict]:
    return db.fetchall("SELECT * FROM push_subscriptions")


def delete_subscription(db: Database, endpoint: str) -> None:
    db.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))


def push(db: Database, *, title: str, body: str = "", url: str = "/",
         tag: str = "automate") -> dict:
    """Fan out a push notification to every subscribed client. Returns a summary."""
    keys = ensure_vapid(db)
    subs = list_subscriptions(db)
    if not subs:
        return {"sent": 0, "failed": 0, "reason": "no subscribers"}

    try:
        from pywebpush import WebPushException, webpush  # type: ignore
    except ImportError:
        log.warning("pywebpush not installed; push disabled. Install with `pip install pywebpush`.")
        return {"sent": 0, "failed": 0, "reason": "pywebpush not installed"}

    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
    sent, failed = 0, 0
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=payload,
                vapid_private_key=_to_pem(keys["private"]),
                vapid_claims={"sub": keys["subject"]},
            )
            sent += 1
        except WebPushException as e:
            failed += 1
            log.warning("push failed for %s: %s", sub["endpoint"][:40], e)
            if e.response and e.response.status_code in (404, 410):
                # Subscription is dead — drop it.
                delete_subscription(db, sub["endpoint"])
        except Exception as e:  # noqa: BLE001
            failed += 1
            log.warning("push error: %s", e)
    return {"sent": sent, "failed": failed}


def _to_pem(b64url_priv: str) -> str:
    """Convert raw 32-byte private scalar (b64url) to PEM that pywebpush accepts."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    raw = base64.urlsafe_b64decode(b64url_priv + "==")
    priv_int = int.from_bytes(raw, "big")
    priv_key = ec.derive_private_key(priv_int, ec.SECP256R1())
    pem = priv_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode()
