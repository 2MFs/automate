# Channels — let WeChat / Telegram / etc. talk to autoMate

> **Status (v4.5.6):** the inbound bridge is shipped — autoMate
> exposes one HTTP endpoint that any gateway can POST messages to.
> The first supported gateway is **OpenClaw**, which has an official
> Tencent-maintained WeChat plugin (connects to *微信个人助手*, not
> personal WeChat — no account-takeover, no ban risk).

## Why a gateway instead of building it ourselves

autoMate's job is files / notes / agent reasoning. Reimplementing
WeChat / WhatsApp / Telegram protocols (each with its own quirks,
auth dance, anti-spam, media uploads, and ToS minefield) is a
full-time job for a team. Several open-source projects already do
this well, and OpenClaw in particular has Tencent's blessing for
WeChat. So we run autoMate alongside one of those, and they each do
what they're best at.

```
┌─────────┐  IM platform protocol   ┌─────────┐  HTTP/JSON   ┌──────────┐
│ WeChat  │ ◄──────────────────────►│ OpenClaw│ ◄───────────►│ autoMate │
│ Telegram│                          │ gateway │              │  (this)  │
│   ...   │                          └─────────┘              └──────────┘
└─────────┘                                                       │
                                                                  ▼
                                                            ┌──────────┐
                                                            │ files /  │
                                                            │ notes /  │
                                                            │ agent /  │
                                                            │  tools   │
                                                            └──────────┘
```

OpenClaw handles the *channel* (the chat platform). autoMate handles
the *intelligence* (what to do with the message). They talk over a
small HTTP contract.

## The bridge protocol

One endpoint, Bearer-auth'd. Token is auto-generated on first install
and shown in **Settings → Channels** for you to copy into the
gateway.

```http
POST /api/channels/inbox
Authorization: Bearer <token>
Content-Type: application/json

{
  "channel":  "wechat",          // any string identifying the platform
  "user_id":  "wxid_abc123",     // opaque, must be stable per IM user
  "text":     "find my Tokyo notes",
  "context":  { ... optional, gateway-specific ... }
}
```

Response (200):

```json
{
  "text":   "Found 1 note: 'Tokyo trip 2026'.",
  "run_id": "9f2d...",
  "ms":     1842
}
```

Errors are returned with proper status codes so the gateway can
render something useful to the IM user:

| Status | Meaning |
|--------|---------|
| 401    | Missing or invalid Bearer token |
| 400    | Empty `text` |
| 503    | Agent failed (usually no LLM provider configured) |

The gateway is responsible for: sending the reply text back through
the IM platform, attaching files, handling group vs DM, etc.
autoMate is responsible for: understanding the message, calling
tools, producing the answer.

Sessions are keyed `(channel, user_id)` so the agent has memory
across messages from the same person — without the gateway
needing to track anything.

## Wiring it up with OpenClaw

1. Install OpenClaw on the same machine as autoMate (or any machine
   that can reach autoMate over the network):
   ```bash
   # follow the official OpenClaw install instructions
   ```
2. Install the channel plugin you want. For WeChat, the official
   Tencent CLI:
   ```bash
   npx -y @tencent-weixin/openclaw-weixin-cli@latest install
   ```
   Then run the channel login (will print a QR code in your
   terminal):
   ```bash
   openclaw channels login --channel openclaw-weixin
   ```
   Scan the QR with the WeChat app to authorize *微信个人助手* to
   forward messages.
3. In autoMate, open **Settings → Channels** and copy the **Inbox
   URL** and **Bearer token**.
4. In OpenClaw's gateway settings, configure an outbound webhook
   for the WeChat channel pointing at your autoMate inbox URL,
   with the Bearer token in the `Authorization` header.
5. Send a message to *微信个人助手* in WeChat. It should arrive at
   autoMate, run the agent, and the reply should come back in
   WeChat.

> The exact OpenClaw configuration steps depend on its current
> release. The autoMate side stays the same regardless: a single
> URL + token.

## Other gateways

The same contract works with anything that can POST JSON:

- **n8n / Zapier / Make** — drag a Webhook node, paste the URL and
  token, set Bearer auth header.
- **Custom script** (Python / Node) — `requests.post(url, json={...},
  headers={"Authorization": "Bearer ..."})`.
- **iOS Shortcuts** — "Get contents of URL" → POST → JSON body.
- **Telegram bot** (without OpenClaw) — wire a tiny `bot.on('message',
  ...)` handler that forwards to the inbox URL.

## What the agent sees

The text we send the LLM is wrapped with a small context line:

```
[message from user 'wxid_abc123' on wechat]

find my Tokyo notes
```

That tells the LLM (a) it's talking through a chat platform, not the
SPA, so replies should be terse and non-Markdown-heavy, and (b) which
user it's talking to, so it can use that as a key for memory tools.
The system prompt (`automate/agent/prompts.py`) covers the rest.

## What's NOT in v4.5.6

- **Outbound attachments** — text-only replies for now. Files /
  voice / images come in v4.5.7.
- **Async mode** — the inbox endpoint blocks until the agent
  finishes. For long-running tool calls (browser automation) the
  gateway will see a slow response. v4.5.7 will add a 202-then-
  callback mode.
- **Auto-installing OpenClaw from autoMate's UI** — for now you
  install OpenClaw yourself, then paste the URL+token. v4.5.x may
  ship a "Channels wizard" that runs the npx commands for you.

## Deprecation note

`automate/bots/` (the old per-platform bot adapters: telegram,
wechat_oa, wecom, wechat_personal) are **frozen** as of v4.5.6.
Existing installs keep working. New deployments should use the
channels bridge above. The old code will be removed in a future
release once the channels path is proven in the wild.
