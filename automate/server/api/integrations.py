"""Integration / tool-connection management.

Two ways to connect:

- ``apikey`` — user pastes a single token in the UI, we encrypt + store it.
  Each provider's ``token_help`` field deep-links the user to the exact
  page where they can mint a token.

- ``oauth`` — single-click "Authorize with X". Implementation depends on
  what the provider supports:
    - ``flow=pkce``   : provider supports PKCE → autoMate runs the dance
                        directly with an embedded public client_id, no
                        secret needed.
    - ``flow=broker`` : provider requires a confidential client →
                        autoMate Cloud (or any self-hosted
                        ``cloud/oauth_broker/``) holds the secret and
                        mediates the dance. See ``automate/oauth/broker.py``.

The old "register your own OAuth app, paste client_id + client_secret"
flow is gone.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ...oauth import (
    OAuthFlow,
    PendingState,
    broker_authorize_url,
    broker_url,
    get_oauth_spec,
    make_challenge,
    make_flow_id,
    make_verifier,
)
from ...store import Vault
from ._deps import state

router = APIRouter(tags=["integrations"], prefix="/integrations")


# Per-integration help strings used by the UI for the API-key path —
# the deep-link goes straight to the page where the user can mint a
# token, with scopes/labels pre-filled where the provider supports it.
TOKEN_HELP = {
    "github":     {"label": "Personal Access Token (classic)",
                   "url": "https://github.com/settings/tokens/new?scopes=repo,read:user,read:org&description=autoMate",
                   "hint": "Click the link → 'Generate token' → copy."},
    "gitlab":     {"label": "Personal Access Token",
                   "url": "https://gitlab.com/-/user_settings/personal_access_tokens",
                   "hint": "Scopes: api, read_user."},
    "gitee":      {"label": "私人令牌",
                   "url": "https://gitee.com/profile/personal_access_tokens/new",
                   "hint": "勾选 user_info, projects, issues。"},
    "notion":     {"label": "Internal Integration Token",
                   "url": "https://www.notion.so/my-integrations",
                   "hint": "New integration → copy 'Internal Integration Token'."},
    "slack":      {"label": "Bot User OAuth Token (xoxb-…)",
                   "url": "https://api.slack.com/apps",
                   "hint": "Your app → OAuth & Permissions → Bot User OAuth Token."},
    "linear":     {"label": "Personal API Key",
                   "url": "https://linear.app/settings/api",
                   "hint": "Settings → API → Create new key."},
    "jira":       {"label": "API token (atlassian.com)",
                   "url": "https://id.atlassian.com/manage-profile/security/api-tokens",
                   "hint": "Create token. Use email:token format if asked."},
    "confluence": {"label": "API token (atlassian.com)",
                   "url": "https://id.atlassian.com/manage-profile/security/api-tokens",
                   "hint": "Same token works for Confluence and Jira."},
    "trello":     {"label": "API key + token",
                   "url": "https://trello.com/app-key",
                   "hint": "Get key → click 'Token' link to generate the matching token."},
    "asana":      {"label": "Personal Access Token",
                   "url": "https://app.asana.com/0/my-apps",
                   "hint": "+ New Personal Access Token."},
    "monday":     {"label": "API Token v2",
                   "url": "https://monday.com/developers/v2",
                   "hint": "Profile → Developer → My access tokens."},
    "hubspot":    {"label": "Private App access token",
                   "url": "https://app.hubspot.com/private-apps",
                   "hint": "Create a private app, set scopes, copy access token."},
    "airtable":   {"label": "Personal Access Token",
                   "url": "https://airtable.com/create/tokens",
                   "hint": "Create token, choose bases + scopes."},
    "stripe":     {"label": "Secret key (sk_live_… / sk_test_…)",
                   "url": "https://dashboard.stripe.com/apikeys",
                   "hint": "Standard or restricted key."},
    "shopify":    {"label": "Admin API access token",
                   "url": "https://help.shopify.com/manual/apps/app-types/custom-apps",
                   "hint": "Create custom app per shop, install, copy token."},
    "telegram":   {"label": "Bot token",
                   "url": "https://t.me/BotFather",
                   "hint": "Talk to @BotFather → /newbot → copy token."},
    "discord":    {"label": "Bot token",
                   "url": "https://discord.com/developers/applications",
                   "hint": "Application → Bot → Reset Token."},
    "teams":      {"label": "Microsoft Graph access token",
                   "url": "https://learn.microsoft.com/en-us/graph/auth/auth-concepts",
                   "hint": "Register an app on Entra, grant permissions, mint a token."},
    "zoom":       {"label": "Server-to-Server OAuth token",
                   "url": "https://marketplace.zoom.us/develop/create",
                   "hint": "Create a S2S OAuth app → copy the access token."},
    "twitter":    {"label": "Bearer Token (v2 API)",
                   "url": "https://developer.twitter.com/en/portal/dashboard",
                   "hint": "Project → Keys & Tokens → Bearer Token."},
    "sendgrid":   {"label": "API Key",
                   "url": "https://app.sendgrid.com/settings/api_keys",
                   "hint": "Full or restricted access."},
    "mailchimp":  {"label": "API key (with -usX suffix)",
                   "url": "https://us1.admin.mailchimp.com/account/api/",
                   "hint": "Profile → Extras → API keys."},
    "twilio":     {"label": "Auth token (account SID + auth token)",
                   "url": "https://console.twilio.com/",
                   "hint": "Console homepage → Account Info."},
    "sentry":     {"label": "Auth token",
                   "url": "https://sentry.io/settings/account/api/auth-tokens/",
                   "hint": "Create new token, scopes: project:read, event:read."},
    "wecom":      {"label": "应用 corpid + secret",
                   "url": "https://work.weixin.qq.com/wework_admin/frame#apps",
                   "hint": "应用管理 → 自建应用 → 复制 corpid 和 Secret(用 ':' 拼接)。"},
    "weixin":     {"label": "公众号 AppID + AppSecret",
                   "url": "https://mp.weixin.qq.com/",
                   "hint": "开发 → 基本配置 → AppID + AppSecret(用 ':' 拼接)。"},
    "weibo":      {"label": "Access token",
                   "url": "https://open.weibo.com/apps",
                   "hint": "应用管理 → 高级信息 → OAuth2 Access Token。"},
    "yuque":      {"label": "User Token",
                   "url": "https://www.yuque.com/settings/tokens",
                   "hint": "新建 Token → 选择团队/空间 → 复制。"},
    "amap":       {"label": "Web 服务 key",
                   "url": "https://console.amap.com/dev/key/app",
                   "hint": "应用管理 → 添加 Key → 服务平台选 Web 服务。"},
    "feishu":     {"label": "tenant_access_token (or app_id:app_secret)",
                   "url": "https://open.feishu.cn/app",
                   "hint": "若不想走 OAuth,直接用应用的 app_id:app_secret(冒号拼)。"},
    "dingtalk":   {"label": "AppKey + AppSecret",
                   "url": "https://open-dev.dingtalk.com/fe/app",
                   "hint": "AppKey:AppSecret 用冒号拼。"},
}


# Built-in catalog so the UI knows what's installable.
INTEGRATION_CATALOG = [
    # SaaS — international
    {"id": "github",     "display_name": "GitHub",         "category": "DevOps",        "auth": "oauth"},
    {"id": "gitlab",     "display_name": "GitLab",         "category": "DevOps",        "auth": "apikey"},
    {"id": "notion",     "display_name": "Notion",         "category": "Productivity",  "auth": "oauth"},
    {"id": "slack",      "display_name": "Slack",          "category": "Messaging",     "auth": "oauth"},
    {"id": "linear",     "display_name": "Linear",         "category": "Project",       "auth": "oauth"},
    {"id": "jira",       "display_name": "Jira",           "category": "Project",       "auth": "apikey"},
    {"id": "confluence", "display_name": "Confluence",     "category": "Productivity",  "auth": "apikey"},
    {"id": "trello",     "display_name": "Trello",         "category": "Project",       "auth": "apikey"},
    {"id": "asana",      "display_name": "Asana",          "category": "Project",       "auth": "apikey"},
    {"id": "monday",     "display_name": "Monday.com",     "category": "Project",       "auth": "apikey"},
    {"id": "hubspot",    "display_name": "HubSpot",        "category": "CRM",           "auth": "apikey"},
    {"id": "airtable",   "display_name": "Airtable",       "category": "Productivity",  "auth": "apikey"},
    {"id": "stripe",     "display_name": "Stripe",         "category": "Payments",      "auth": "apikey"},
    {"id": "shopify",    "display_name": "Shopify",        "category": "Commerce",      "auth": "apikey"},
    {"id": "telegram",   "display_name": "Telegram",       "category": "Messaging",     "auth": "apikey"},
    {"id": "discord",    "display_name": "Discord",        "category": "Messaging",     "auth": "apikey"},
    {"id": "teams",      "display_name": "Microsoft Teams","category": "Messaging",     "auth": "apikey"},
    {"id": "zoom",       "display_name": "Zoom",           "category": "Meetings",      "auth": "apikey"},
    {"id": "twitter",    "display_name": "Twitter / X",    "category": "Social",        "auth": "apikey"},
    {"id": "sendgrid",   "display_name": "SendGrid",       "category": "Email",         "auth": "apikey"},
    {"id": "mailchimp",  "display_name": "Mailchimp",      "category": "Email",         "auth": "apikey"},
    {"id": "twilio",     "display_name": "Twilio",         "category": "SMS",           "auth": "apikey"},
    {"id": "sentry",     "display_name": "Sentry",         "category": "DevOps",        "auth": "apikey"},
    # SaaS — China
    {"id": "feishu",     "display_name": "飞书 / Lark",    "category": "Messaging",     "auth": "oauth"},
    {"id": "dingtalk",   "display_name": "钉钉",           "category": "Messaging",     "auth": "oauth"},
    {"id": "wecom",      "display_name": "企业微信",       "category": "Messaging",     "auth": "apikey"},
    {"id": "weixin",     "display_name": "微信公众号",     "category": "Messaging",     "auth": "apikey"},
    {"id": "weibo",      "display_name": "微博",           "category": "Social",        "auth": "apikey"},
    {"id": "gitee",      "display_name": "Gitee",          "category": "DevOps",        "auth": "apikey"},
    {"id": "yuque",      "display_name": "语雀",           "category": "Productivity",  "auth": "apikey"},
    {"id": "amap",       "display_name": "高德地图",       "category": "Location",      "auth": "apikey"},
]


class ApiKeyConnect(BaseModel):
    token: str
    metadata: dict | None = None


def _enrich(entry: dict) -> dict:
    """Tack on per-integration metadata used by the UI."""
    out = dict(entry)
    cid = entry["id"]
    if entry.get("auth") == "oauth":
        spec = get_oauth_spec(cid)
        out["oauth_flow"] = spec.flow if spec else None    # "pkce" | "broker"
    out["token_help"] = TOKEN_HELP.get(cid)
    return out


@router.get("/catalog")
def catalog():
    return [_enrich(e) for e in INTEGRATION_CATALOG]


@router.get("")
def list_connections(s=Depends(state)):
    by_id = {c["id"]: c for c in s.db.list_connections()}
    out = []
    for entry in INTEGRATION_CATALOG:
        row = by_id.get(entry["id"])
        out.append({
            **_enrich(entry),
            "status": row["status"] if row else "disconnected",
            "token_set": bool(row and row["token_set"]),
            "metadata": json.loads(row["metadata_json"]) if row else {},
            "updated_at": row["updated_at"] if row else None,
        })
    return out


@router.post("/{cid}/apikey")
def connect_apikey(cid: str, body: ApiKeyConnect, s=Depends(state)):
    entry = next((e for e in INTEGRATION_CATALOG if e["id"] == cid), None)
    if not entry:
        raise HTTPException(404, "unknown integration")
    s.db.upsert_connection(
        id=cid, display_name=entry["display_name"], auth_kind="apikey",
        status="connected", token=body.token, metadata=body.metadata or {},
    )
    return {"ok": True}


@router.get("/{cid}/connect")
def begin_oauth(cid: str, request: Request, s=Depends(state)):
    """Begin an OAuth flow. Returns ``{authorize_url, flow_id}``.

    The browser opens ``authorize_url`` in a popup. After the user
    consents, the provider (or broker) redirects back to
    ``/oauth/<cid>/callback``. The popup posts a message to its opener
    on success and self-closes.
    """
    spec = get_oauth_spec(cid)
    if not spec:
        raise HTTPException(404, "OAuth not supported for this integration; use /apikey")

    redirect_uri = f"{request.base_url._url.rstrip('/')}/oauth/{cid}/callback"
    state_token = Vault.random_token()
    now = __import__("time").time()

    if spec.flow == "pkce":
        if not spec.pkce_client_id:
            raise HTTPException(503, f"{cid}: PKCE client_id not configured in this build.")
        verifier = make_verifier()
        challenge = make_challenge(verifier)
        OAuthFlow.remember(state_token, PendingState(
            provider_id=cid, redirect_uri=redirect_uri, flow="pkce",
            pkce_verifier=verifier, created_at=now,
        ))
        url = OAuthFlow.authorize_url_pkce(
            spec, client_id=spec.pkce_client_id, redirect_uri=redirect_uri,
            state=state_token, code_challenge=challenge,
        )
        return {"authorize_url": url, "flow": "pkce"}

    # broker flow
    flow_id = make_flow_id()
    try:
        url = broker_authorize_url(
            provider_id=cid, flow_id=flow_id,
            local_redirect=redirect_uri, scopes=spec.scopes,
        )
    except Exception as e:  # noqa: BLE001 — propagate broker failures cleanly
        raise HTTPException(
            503,
            f"OAuth broker unreachable ({broker_url()}): {e}. "
            f"Either set AUTOMATE_OAUTH_BROKER_URL to a reachable broker, or "
            f"use the API-key path for this integration.",
        )
    OAuthFlow.remember(state_token, PendingState(
        provider_id=cid, redirect_uri=redirect_uri, flow="broker",
        broker_flow_id=flow_id, created_at=now,
    ))
    # The broker is going to redirect back with ``flow_id`` (NOT
    # ``state``) since it doesn't know our state token. We stash a
    # second mapping so the callback can find the pending entry by
    # flow_id alone.
    OAuthFlow.remember(f"flow:{flow_id}", OAuthFlow.PENDING[state_token])
    return {"authorize_url": url, "flow": "broker", "broker_url": broker_url()}


@router.post("/{cid}/disconnect")
def disconnect(cid: str, s=Depends(state)):
    s.db.delete_connection(cid)
    return {"ok": True}
