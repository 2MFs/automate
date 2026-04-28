"""In-process registry of in-flight OAuth attempts.

For PKCE flows we hold the verifier between ``/connect`` (where it's
generated) and ``/oauth/<id>/callback`` (where it's used in token
exchange). For broker flows we just remember which ``flow_id`` belongs
to which provider so we can finalise on callback.

Entries auto-expire after 10 minutes.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .catalog import OAuthSpec


@dataclass
class PendingState:
    provider_id: str
    redirect_uri: str
    flow: str                              # "pkce" or "broker"
    pkce_verifier: str | None = None       # only set for flow="pkce"
    broker_flow_id: str | None = None      # only set for flow="broker"
    created_at: float = 0.0


class OAuthFlow:
    PENDING: dict[str, PendingState] = {}

    @classmethod
    def remember(cls, state: str, ps: PendingState) -> None:
        cls._gc()
        cls.PENDING[state] = ps

    @classmethod
    def pop(cls, state: str) -> PendingState | None:
        cls._gc()
        return cls.PENDING.pop(state, None)

    @classmethod
    def _gc(cls) -> None:
        now = time.time()
        stale = [k for k, v in cls.PENDING.items() if now - v.created_at > 600]
        for k in stale:
            cls.PENDING.pop(k, None)

    @staticmethod
    def authorize_url_pkce(spec: OAuthSpec, *, client_id: str, redirect_uri: str,
                           state: str, code_challenge: str,
                           scopes: tuple[str, ...] | None = None) -> str:
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        scope_list = scopes if scopes is not None else spec.scopes
        if scope_list:
            params["scope"] = " ".join(scope_list)
        params.update(spec.extra_auth_params)
        return f"{spec.authorize_url}?{urllib.parse.urlencode(params)}"


def exchange_code_pkce(spec: OAuthSpec, *, code: str, redirect_uri: str,
                       client_id: str, code_verifier: str) -> dict:
    """PKCE token exchange — no client_secret."""
    body = urllib.parse.urlencode({
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }).encode()
    req = urllib.request.Request(
        spec.token_url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return dict(urllib.parse.parse_qsl(raw))
