# autoMate OAuth broker

## Why does this exist

GitHub, Notion, Slack, 飞书 and 钉钉 require a `client_secret` at the
OAuth token-exchange step, and forbid embedding it in distributed
software. A self-hosted tool that wants the **"click Authorize and
you're done"** UX therefore needs a small companion service that holds
those secrets and mediates the dance.

That's what `cloud/oauth_broker/` is. Each autoMate maintainer (or
self-hoster) runs **one** broker. Every autoMate user's hub points at
it via `AUTOMATE_OAUTH_BROKER_URL`.

For providers that support PKCE (Linear, Atlassian, Microsoft Graph,
Google, Twitter/X, Discord), no broker is needed — autoMate ships a
public `client_id` and runs the dance directly with the provider.

## Threat model

The broker only sees user OAuth tokens during the ~30-second window
when an authorization is in flight. After the local hub fetches the
token via `/oauth/result?flow_id=...`, the broker forgets it. The
only secret in transit is `flow_id`, a 256-bit URL-safe random value
that travels through HTTPS only. A malicious or compromised broker
could steal tokens, so users should only point at brokers they trust.
The autoMate Cloud broker (default) is operated by the autoMate
maintainers.

## Deployment

```bash
cd cloud/oauth_broker
docker build -t automate-oauth-broker .
docker run -d \
  -p 443:8080 \
  -e PUBLIC_BASE_URL=https://broker.example.com \
  -e OAUTH_GITHUB_CLIENT_ID=Iv1.xxxxxxxxxxxxxxxx \
  -e OAUTH_GITHUB_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  -e OAUTH_NOTION_CLIENT_ID=... \
  -e OAUTH_NOTION_CLIENT_SECRET=... \
  -e OAUTH_SLACK_CLIENT_ID=... \
  -e OAUTH_SLACK_CLIENT_SECRET=... \
  -e OAUTH_FEISHU_CLIENT_ID=... \
  -e OAUTH_FEISHU_CLIENT_SECRET=... \
  -e OAUTH_DINGTALK_CLIENT_ID=... \
  -e OAUTH_DINGTALK_CLIENT_SECRET=... \
  --name automate-oauth-broker \
  automate-oauth-broker
```

Or without Docker:

```bash
cd cloud/oauth_broker
pip install -r requirements.txt
PUBLIC_BASE_URL=https://broker.example.com \
OAUTH_GITHUB_CLIENT_ID=... OAUTH_GITHUB_CLIENT_SECRET=... \
... \
uvicorn main:app --host 0.0.0.0 --port 8080
```

`PUBLIC_BASE_URL` must be HTTPS and reachable from the user's browser,
because providers will redirect there. A Cloudflare Tunnel /
Cloudflare Pages Function / Fly.io / Cloud Run deployment all work.

## Per-provider OAuth app registration

Register an OAuth app at each provider with the redirect URI
`{PUBLIC_BASE_URL}/oauth/<provider>/callback`.

| Provider | Where to register | Redirect URI to set |
|---|---|---|
| GitHub | https://github.com/settings/applications/new | `{base}/oauth/github/callback` |
| Notion | https://www.notion.so/my-integrations | `{base}/oauth/notion/callback` |
| Slack | https://api.slack.com/apps | `{base}/oauth/slack/callback` |
| 飞书 | https://open.feishu.cn/app | `{base}/oauth/feishu/callback` |
| 钉钉 | https://open-dev.dingtalk.com/fe/app | `{base}/oauth/dingtalk/callback` |

Required OAuth scopes per provider are coded in `cloud/oauth_broker/main.py:SPECS`.

## Pointing autoMate at your broker

Each autoMate hub uses `AUTOMATE_OAUTH_BROKER_URL` to know where to go:

```bash
AUTOMATE_OAUTH_BROKER_URL=https://broker.example.com automate serve
```

Default (when env var unset) is `https://broker.automate.cloud`,
operated by the autoMate maintainers.

## Health check

```bash
curl https://broker.example.com/health
# {"ok":true,"providers":["github","notion","slack","feishu","dingtalk"]}
```

If a provider is missing from the response, its
`OAUTH_<PROVIDER>_CLIENT_ID/SECRET` env vars aren't set.

## When the broker is down

The local hub surfaces a clear error message and offers the API-key
fallback path (deep-link to the provider's PAT page). OAuth and
API-key paths produce identical end-state in the `connections` table —
either way autoMate has authorization for the provider.
