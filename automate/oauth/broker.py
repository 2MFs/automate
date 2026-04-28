"""OAuth broker client — the real "click-Auth-and-done" path.

Why a broker exists
-------------------
Most popular providers (GitHub, Notion, Slack, 飞书, 钉钉) require a
``client_secret`` for the token exchange, and forbid embedding it in
distributed clients. A self-hosted tool that wants the consumer-OAuth
UX ("Sign in with GitHub", one click) therefore needs a hosted
companion service that holds those secrets and brokers the dance.

Flow
----
1. Local hub generates a random ``flow_id`` (32 random bytes,
   url-safe-base64). It calls
   ``GET {broker}/oauth/{provider}/start?flow_id=...&local_redirect=...``
   which returns the authorize URL the user's browser should be sent to.
2. Provider redirects to the broker's callback. Broker exchanges the
   code for a token using its OWN client_id + client_secret (registered
   by the autoMate maintainers, never shipped in this binary).
3. Broker stores ``flow_id → token_payload`` in memory with a 5-minute
   TTL, then redirects the user's browser back to ``local_redirect``
   with ``flow_id`` in the query string.
4. Local hub's callback fetches
   ``GET {broker}/oauth/result?flow_id=...`` over HTTPS. Broker returns
   the token payload exactly once and forgets it.

The ``flow_id`` is the only secret in transit; it travels through the
user's browser (HTTPS) and is fetched by the local hub (HTTPS). This
gives the same security model as standard OAuth — the broker only sees
tokens during the 30-second window of an in-flight authorization, and
``flow_id`` is single-use and time-bound.

Default broker
--------------
Defaults to ``AUTOMATE_OAUTH_BROKER_URL`` (env), falling back to the
autoMate Cloud broker. Set the env var to your own deployment if you
self-host the broker (see ``cloud/oauth_broker/`` and
``docs/oauth-broker.md``).
"""
from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

DEFAULT_BROKER_URL = "https://broker.automate.cloud"


def broker_url() -> str:
    """Effective broker URL, with trailing slash trimmed."""
    return (os.environ.get("AUTOMATE_OAUTH_BROKER_URL") or DEFAULT_BROKER_URL).rstrip("/")


def make_flow_id() -> str:
    return secrets.token_urlsafe(32)


@dataclass
class BrokerStartResponse:
    """What the broker returns from /oauth/{provider}/start."""
    authorize_url: str  # the URL to send the user's browser to
    flow_id: str        # echoed back so the caller can stash it


class BrokerError(RuntimeError):
    """Broker is unreachable or returned a non-2xx response."""


def request_authorize_url(*, provider_id: str, flow_id: str,
                          local_redirect: str, scopes: tuple[str, ...] = ()) -> str:
    """Ask the broker for a provider authorize URL.

    The broker has the provider's client_id + scopes etc. baked in. We
    just hand it our flow_id (so it knows where to deliver the result)
    and the local_redirect (so it can bounce the user back to our hub
    when the dance finishes).
    """
    base = broker_url()
    params = urllib.parse.urlencode({
        "flow_id": flow_id,
        "local_redirect": local_redirect,
        "scopes": " ".join(scopes),
    })
    url = f"{base}/oauth/{provider_id}/start?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:  # 4xx / 5xx
        raise BrokerError(f"broker returned {e.code}: {e.read().decode()[:200]}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise BrokerError(f"broker unreachable at {base}: {e}") from e
    auth_url = payload.get("authorize_url")
    if not auth_url:
        raise BrokerError(f"broker /start payload missing authorize_url: {payload}")
    return auth_url


def fetch_result(*, flow_id: str, max_attempts: int = 30) -> dict:
    """Fetch the token payload for a completed flow.

    The broker may redirect the user back to local_redirect *before* its
    own callback handler has finished writing the result (race), so we
    retry a few times with short sleeps.
    """
    base = broker_url()
    url = f"{base}/oauth/result?flow_id={urllib.parse.quote(flow_id)}"
    last_err: Exception | None = None
    for _ in range(max_attempts):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                last_err = e
                time.sleep(0.5)
                continue
            raise BrokerError(f"broker returned {e.code} on /result: {e.read().decode()[:200]}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            time.sleep(0.5)
    raise BrokerError(f"broker /result timed out after {max_attempts} tries: {last_err}")
