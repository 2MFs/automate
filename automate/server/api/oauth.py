"""OAuth callback handler.

Lives outside ``/api`` so the redirect URI registered with each provider
(or with the broker) can be a clean
``http://127.0.0.1:8765/oauth/<id>/callback``.

Two completion paths share this handler:

- PKCE: provider returns ``code`` + ``state``. We exchange ``code`` +
  the stashed ``code_verifier`` for the token directly with the
  provider.

- Broker: broker returns ``flow_id`` (the broker built that mapping
  during ``GET /oauth/<id>/connect``). We pull the token from the
  broker's ``/oauth/result`` endpoint over HTTPS, then forget the
  pending entry.

In both cases the page that renders self-closes after posting a
``{kind: "automate-oauth", ok: true|false, provider, message}`` message
to ``window.opener`` so the SPA can update the integrations modal
without a refresh.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from ...oauth import (
    OAuthFlow,
    broker_fetch_result,
    exchange_code_pkce,
    get_oauth_spec,
)
from ._deps import state as app_state

router = APIRouter(tags=["oauth"])


_RESULT_HTML = """\
<!doctype html>
<html><head><meta charset=utf-8><title>autoMate · {title}</title>
<style>
  body{{font-family:-apple-system,system-ui,sans-serif;max-width:520px;
        margin:80px auto;color:#111;padding:0 20px;}}
  h1{{font-size:22px;margin:0 0 12px;}} p{{color:#555;line-height:1.55;}}
  .pill{{display:inline-block;padding:4px 10px;border-radius:999px;
        font-size:12px;background:{bg};color:{fg};margin-bottom:16px;}}
</style></head>
<body><span class=pill>{pill}</span><h1>{title}</h1><p>{body}</p>
<p style="color:#888;font-size:12px;">This window will close automatically.</p>
<script>
  // Tell the SPA in the opener tab how it went, then self-close.
  try {{
    if (window.opener && !window.opener.closed) {{
      window.opener.postMessage(
        {{kind: "automate-oauth", ok: {ok_js}, provider: "{provider}", message: {msg_js} }},
        window.location.origin
      );
    }}
  }} catch (e) {{ /* opener gone or cross-origin — ignore */ }}
  setTimeout(() => {{ try {{ window.close(); }} catch (e) {{}} }}, 1500);
</script>
</body></html>"""


def _page(*, title: str, body: str, ok: bool, provider: str, code: int = 200) -> HTMLResponse:
    pill, bg, fg = ("Success", "#d1fae5", "#065f46") if ok else ("Error", "#fde8e8", "#9b1c1c")
    import json as _json
    msg_js = _json.dumps(body)
    return HTMLResponse(_RESULT_HTML.format(
        title=title, body=body, pill=pill, bg=bg, fg=fg,
        ok_js="true" if ok else "false",
        provider=provider, msg_js=msg_js,
    ), status_code=code)


def _err(provider: str, title: str, body: str, code: int = 400) -> HTMLResponse:
    return _page(title=title, body=body, ok=False, provider=provider, code=code)


@router.get("/oauth/{cid}/callback", response_class=HTMLResponse)
def callback(
    cid: str,
    code: str | None = Query(None),
    state: str | None = Query(None),
    flow_id: str | None = Query(None),
    error: str | None = Query(None),
    s=Depends(app_state),
):
    spec = get_oauth_spec(cid)
    if error:
        return _err(cid, "Authorization failed", f"Provider returned: {error}")
    if not spec:
        return _err(cid, "Unknown provider", f"No OAuth spec registered for '{cid}'.")

    # Locate pending. PKCE comes back with `state`; broker with `flow_id`.
    if state:
        pending = OAuthFlow.pop(state)
    elif flow_id:
        pending = OAuthFlow.pop(f"flow:{flow_id}")
    else:
        return _err(cid, "Missing state", "No state or flow_id in callback.")

    if not pending or pending.provider_id != cid:
        return _err(cid, "State mismatch",
                    "The OAuth state token did not match an in-flight request. "
                    "Try clicking Connect again — these tokens expire after 10 minutes.")

    # ---- PKCE path: provider returned an auth code ----
    if pending.flow == "pkce":
        if not code:
            return _err(cid, "Missing code", "Provider didn't return an auth code.")
        if not pending.pkce_verifier or not spec.pkce_client_id:
            return _err(cid, "PKCE state lost",
                        "The verifier or client_id wasn't available at exchange time.")
        try:
            payload = exchange_code_pkce(
                spec, code=code, redirect_uri=pending.redirect_uri,
                client_id=spec.pkce_client_id, code_verifier=pending.pkce_verifier,
            )
        except Exception as e:  # noqa: BLE001
            return _err(cid, "Token exchange failed", f"{type(e).__name__}: {e}")
        return _store_payload(cid, spec, payload, s)

    # ---- broker path: pull the token from the broker ----
    if pending.flow == "broker":
        if not pending.broker_flow_id:
            return _err(cid, "Broker flow_id lost",
                        "The pending entry had no broker_flow_id.")
        try:
            payload = broker_fetch_result(flow_id=pending.broker_flow_id)
        except Exception as e:  # noqa: BLE001
            return _err(cid, "Broker fetch failed",
                        f"{type(e).__name__}: {e}. The broker may be down — "
                        f"try the API-key path for this provider as a fallback.")
        return _store_payload(cid, spec, payload, s)

    return _err(cid, "Unknown flow", f"flow={pending.flow}")


def _store_payload(cid: str, spec, payload: dict, s) -> HTMLResponse:
    """Persist the token payload to the connections table."""
    access_token = payload.get(spec.token_field) or payload.get("access_token")
    refresh_token = payload.get(spec.refresh_field or "")
    expires_in = payload.get("expires_in")
    expires_at = (time.time() + float(expires_in)) if expires_in else None

    if not access_token:
        return _err(cid, "No access_token in response",
                    f"Raw response keys: {list(payload.keys())}")

    s.db.upsert_connection(
        id=cid, display_name=spec.display_name, auth_kind="oauth",
        status="connected", token=access_token, refresh=refresh_token,
        expires_at=expires_at,
        metadata={"raw": {k: v for k, v in payload.items()
                          if k not in {spec.token_field, spec.refresh_field or ""}}},
    )
    return _page(
        title=f"{spec.display_name} connected",
        body="autoMate now has authorization for this account. You may close this tab.",
        ok=True, provider=cid,
    )
