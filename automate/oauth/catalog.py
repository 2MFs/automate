"""OAuth provider catalog.

Two flows are supported:

- ``flow = "pkce"`` — PKCE (RFC 7636). No client_secret needed; we ship
  a single embedded ``pkce_client_id`` in the binary. The provider must
  support PKCE for public clients with localhost redirect URIs.
  Used for: Linear, Atlassian (Jira/Confluence), Microsoft Graph,
  Google, Twitter/X, Discord — every modern OAuth-2.1-compliant
  provider.

- ``flow = "broker"`` — the dance is mediated by a hosted broker that
  holds the provider's ``client_secret``. autoMate Cloud runs one at
  ``https://broker.automate.cloud`` by default; self-hosters can run
  their own (see ``cloud/oauth_broker/`` and ``docs/oauth-broker.md``).
  Used for providers that still require a confidential client at the
  token endpoint: GitHub, Notion, Slack, 飞书, 钉钉.

The "register your own OAuth app, paste client_id + secret" flow is
gone — that was the source of the painful UX the user hit before.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OAuthSpec:
    id: str                       # connection id, matches integrations/<id>.py
    display_name: str
    flow: str                     # "pkce" or "broker"
    authorize_url: str            # used by the PKCE flow; broker uses its own
    token_url: str                # used by the PKCE flow; broker uses its own
    scopes: tuple[str, ...]
    docs_url: str
    extra_auth_params: dict = field(default_factory=dict)
    token_field: str = "access_token"
    refresh_field: str | None = "refresh_token"
    # PKCE-only — the embedded client_id we ship.
    pkce_client_id: str | None = None


OAUTH_PROVIDERS: tuple[OAuthSpec, ...] = (
    # ---------- broker-mediated providers (need client_secret) ----------
    OAuthSpec(
        id="github",
        display_name="GitHub",
        flow="broker",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        scopes=("repo", "read:user", "read:org"),
        docs_url="https://docs.github.com/en/apps/oauth-apps",
    ),
    OAuthSpec(
        id="notion",
        display_name="Notion",
        flow="broker",
        authorize_url="https://api.notion.com/v1/oauth/authorize",
        token_url="https://api.notion.com/v1/oauth/token",
        scopes=(),
        docs_url="https://developers.notion.com/docs/authorization",
        extra_auth_params={"owner": "user"},
    ),
    OAuthSpec(
        id="slack",
        display_name="Slack",
        flow="broker",
        authorize_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        scopes=("chat:write", "channels:read", "users:read"),
        docs_url="https://api.slack.com/authentication/oauth-v2",
    ),
    OAuthSpec(
        id="feishu",
        display_name="飞书 / Lark",
        flow="broker",
        authorize_url="https://open.feishu.cn/open-apis/authen/v1/index",
        token_url="https://open.feishu.cn/open-apis/authen/v2/oauth/token",
        scopes=(),
        docs_url="https://open.feishu.cn/document/server-docs/authentication-management/access-token/web-app-access-token",
    ),
    OAuthSpec(
        id="dingtalk",
        display_name="钉钉",
        flow="broker",
        authorize_url="https://login.dingtalk.com/oauth2/auth",
        token_url="https://api.dingtalk.com/v1.0/oauth2/userAccessToken",
        scopes=("openid",),
        docs_url="https://open.dingtalk.com/document/orgapp/obtain-identity-credentials",
        extra_auth_params={"prompt": "consent"},
    ),

    # ---------- PKCE-supporting providers (no broker needed) ----------
    OAuthSpec(
        id="linear",
        display_name="Linear",
        flow="pkce",
        authorize_url="https://linear.app/oauth/authorize",
        token_url="https://api.linear.app/oauth/token",
        scopes=("read", "write"),
        docs_url="https://developers.linear.app/docs/oauth/authentication",
        # NOTE: replace with the real shipped public client_id once
        # registered. Until then, Linear-OAuth degrades to a clear
        # "needs PKCE app registration" notice; API-key still works.
        pkce_client_id="automate-linear-pkce-replace-me",
    ),
)


def get_oauth_spec(id: str) -> OAuthSpec | None:
    return next((p for p in OAUTH_PROVIDERS if p.id == id), None)
