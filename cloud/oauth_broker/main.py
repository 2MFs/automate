"""autoMate OAuth broker.

A tiny FastAPI service that holds the OAuth ``client_secret`` for each
upstream provider and brokers the dance for self-hosted autoMate hubs
that can't ship secrets in their binaries.

Architecture
------------

  Local hub                          Broker (this app)            Provider (GitHub, …)
   │                                 │                            │
   │ GET  /oauth/<p>/start           │                            │
   │ ──────────────────────────────▶ │                            │
   │ ◀── { authorize_url }           │                            │
   │                                 │                            │
   │      (user's browser opens authorize_url)                    │
   │                                 │ ◀── ?code= callback ─────  │
   │                                 │ POST /token  ────────────▶ │
   │                                 │ ◀── token payload ─────────│
   │                                 │                            │
   │ ◀── 302 to local_redirect?flow_id=...  (broker stashes payload by flow_id) │
   │                                                              │
   │ GET  /oauth/result?flow_id=...                                │
   │ ──────────────────────────────────────────────────────────▶  │
   │ ◀── { token: ..., ... }   (single-use, deleted on read)      │

Deployment
----------

Set provider creds via env vars:

    OAUTH_GITHUB_CLIENT_ID=...
    OAUTH_GITHUB_CLIENT_SECRET=...
    OAUTH_NOTION_CLIENT_ID=...
    OAUTH_NOTION_CLIENT_SECRET=...
    OAUTH_SLACK_CLIENT_ID=...
    OAUTH_SLACK_CLIENT_SECRET=...
    OAUTH_FEISHU_CLIENT_ID=...
    OAUTH_FEISHU_CLIENT_SECRET=...
    OAUTH_DINGTALK_CLIENT_ID=...
    OAUTH_DINGTALK_CLIENT_SECRET=...

Then::

    pip install fastapi uvicorn httpx
    PUBLIC_BASE_URL=https://broker.example.com  uvicorn cloud.oauth_broker.main:app --host 0.0.0.0 --port 8080

Each provider needs an OAuth app registered with redirect URI
``{PUBLIC_BASE_URL}/oauth/<provider>/callback``. See
``docs/oauth-broker.md`` for per-provider registration links.
"""
from __future__ import annotations

import os
import time
import urllib.parse
from dataclasses import dataclass
from threading import Lock

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse


# ---------------- provider specs ----------------

@dataclass(frozen=True)
class Spec:
    id: str
    authorize_url: str
    token_url: str
    default_scopes: tuple[str, ...]
    extra_auth_params: dict
    # Some providers (Slack, GitHub) accept secret in body; some (Notion)
    # require Basic auth. Set "header" to use HTTP Basic for the token call.
    auth_method: str = "body"   # "body" or "header"


SPECS: dict[str, Spec] = {
    "github":   Spec("github",
                     "https://github.com/login/oauth/authorize",
                     "https://github.com/login/oauth/access_token",
                     ("repo", "read:user", "read:org"), {}),
    "notion":   Spec("notion",
                     "https://api.notion.com/v1/oauth/authorize",
                     "https://api.notion.com/v1/oauth/token",
                     (), {"owner": "user"}, auth_method="header"),
    "slack":    Spec("slack",
                     "https://slack.com/oauth/v2/authorize",
                     "https://slack.com/api/oauth.v2.access",
                     ("chat:write", "channels:read", "users:read"), {}),
    "feishu":   Spec("feishu",
                     "https://open.feishu.cn/open-apis/authen/v1/index",
                     "https://open.feishu.cn/open-apis/authen/v2/oauth/token",
                     (), {}),
    "dingtalk": Spec("dingtalk",
                     "https://login.dingtalk.com/oauth2/auth",
                     "https://api.dingtalk.com/v1.0/oauth2/userAccessToken",
                     ("openid",), {"prompt": "consent"}),
}


def _creds(provider: str) -> tuple[str, str]:
    cid = os.environ.get(f"OAUTH_{provider.upper()}_CLIENT_ID") or ""
    csec = os.environ.get(f"OAUTH_{provider.upper()}_CLIENT_SECRET") or ""
    if not cid or not csec:
        raise HTTPException(503, f"broker not configured for {provider}: "
                                  f"set OAUTH_{provider.upper()}_CLIENT_ID/SECRET env vars")
    return cid, csec


def _public_base_url() -> str:
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not base:
        raise HTTPException(500, "PUBLIC_BASE_URL env var is required")
    return base


# ---------------- in-memory state ----------------

@dataclass
class Pending:
    provider: str
    local_redirect: str
    created_at: float
    state_token: str   # the broker's own state, sent to the provider


@dataclass
class Result:
    payload: dict
    created_at: float


_lock = Lock()
_pending: dict[str, Pending] = {}   # flow_id → Pending
_results: dict[str, Result] = {}    # flow_id → Result


def _gc() -> None:
    now = time.time()
    with _lock:
        for d in (_pending, _results):
            stale = [k for k, v in d.items() if now - v.created_at > 600]
            for k in stale:
                d.pop(k, None)


# ---------------- app ----------------

app = FastAPI(title="autoMate OAuth broker")


@app.get("/health")
def health():
    return {"ok": True, "providers": list(SPECS.keys())}


@app.get("/oauth/{provider}/start")
def start(provider: str, flow_id: str = Query(...), local_redirect: str = Query(...),
          scopes: str = Query("")):
    """Give the local hub an authorize URL it can send the user's browser to."""
    spec = SPECS.get(provider)
    if not spec:
        raise HTTPException(404, f"unknown provider {provider}")
    cid, _ = _creds(provider)
    base = _public_base_url()
    redirect_uri = f"{base}/oauth/{provider}/callback"
    state_token = f"{provider}:{flow_id}"
    _gc()
    with _lock:
        _pending[flow_id] = Pending(
            provider=provider, local_redirect=local_redirect,
            created_at=time.time(), state_token=state_token,
        )
    scope_list = tuple(s for s in scopes.split() if s) or spec.default_scopes
    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state_token,
    }
    if scope_list:
        params["scope"] = " ".join(scope_list)
    params.update(spec.extra_auth_params)
    return {"authorize_url": f"{spec.authorize_url}?{urllib.parse.urlencode(params)}"}


@app.get("/oauth/{provider}/callback")
def callback(provider: str, request: Request,
             code: str = Query(None), state: str = Query(None),
             error: str = Query(None)):
    """Provider callback. Exchange code → token, stash by flow_id, bounce back to local."""
    spec = SPECS.get(provider)
    if not spec:
        raise HTTPException(404, f"unknown provider {provider}")
    if error:
        raise HTTPException(400, f"{provider} returned error: {error}")
    if not code or not state or ":" not in state:
        raise HTTPException(400, "missing code or malformed state")
    state_provider, flow_id = state.split(":", 1)
    if state_provider != provider:
        raise HTTPException(400, "state/provider mismatch")
    with _lock:
        pending = _pending.pop(flow_id, None)
    if not pending:
        raise HTTPException(400, "no pending flow for this state — expired or unknown")

    cid, csec = _creds(provider)
    base = _public_base_url()
    redirect_uri = f"{base}/oauth/{provider}/callback"

    body = {
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    headers = {"Accept": "application/json"}
    if spec.auth_method == "body":
        body["client_id"] = cid
        body["client_secret"] = csec
        auth = None
    else:
        auth = (cid, csec)

    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(spec.token_url, data=body, auth=auth, headers=headers)
        r.raise_for_status()
    except httpx.HTTPError as e:  # noqa: BLE001
        raise HTTPException(502, f"{provider} token exchange failed: {e}")

    try:
        payload = r.json()
    except ValueError:
        # GitHub may return form-encoded
        payload = dict(urllib.parse.parse_qsl(r.text))

    with _lock:
        _results[flow_id] = Result(payload=payload, created_at=time.time())

    # Bounce the user's browser back to the local hub. Include flow_id —
    # the local hub will fetch the actual token via /oauth/result.
    sep = "&" if "?" in pending.local_redirect else "?"
    return RedirectResponse(f"{pending.local_redirect}{sep}flow_id={urllib.parse.quote(flow_id)}", status_code=302)


@app.get("/oauth/result")
def result(flow_id: str = Query(...)):
    """Local hub polls this to retrieve the token. Single-use; deleted on read."""
    _gc()
    with _lock:
        rec = _results.pop(flow_id, None)
    if not rec:
        raise HTTPException(404, "flow_id not found (expired, already consumed, or never completed)")
    return JSONResponse(rec.payload)
