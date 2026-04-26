# autoMate Cloud — open-source / paid boundary

> Status (v4.4): the **client hooks** ship in this repo — the auth
> client, the API endpoints, the Settings UI, and the `tier="pro"`
> tool decoration. The **cloud server itself is a separate project**
> (closed-source, will live in `automate-cloud`). Until that's online,
> the Settings sheet shows "Cloud sync coming soon" and pro-tier
> tools politely degrade.

## Why open client + closed server

The user (or anyone reading this) deserves a straight answer about
what's in this repo and what isn't, and why.

We're modeling on **SiYuan Notes**: client is fully open-source
(AGPL), official cloud sync is a paid SaaS the SiYuan team operates.
Anyone can fork the client and self-host their own sync — and SiYuan
explicitly supports that, via S3 / WebDAV — but most people pay for
the official service because they don't want to run a server.

The lesson from looking at SiYuan, Bitwarden, Standard Notes,
Obsidian:

| Pattern | Example | What happens |
|---|---|---|
| Open client + open server | Bitwarden, Standard Notes | Self-hosting is real, paid cloud lives on convenience + ops + enterprise SSO |
| Open client + closed server | **SiYuan**, autoMate (this) | Self-hosting needs work but is possible; paid cloud lives on convenience + free quota + brand |
| Closed client | Obsidian | Community ships LiveSync to bypass the paid tier, eroding the moat |

The "open client + closed server" lane is what we want. The moat is:

1. **Brand** — people know "autoMate Cloud" works; they don't trust
   a random fork
2. **Operations** — running a sync server reliably is expensive +
   annoying
3. **Free quota** — generous enough that most users never feel the
   pain of self-hosting
4. **Paid features** that genuinely live in the cloud (transcription,
   public-content extraction) and need an inference budget we can
   amortize across users

What we **don't** rely on as a moat: keeping the sync API secret. The
client code is right here in this repo. Anyone can read it, build a
compatible cloud, and run it. We're betting that won't matter.

## What's in this repo (v4.4)

| File | What it does |
|---|---|
| `automate/auth.py` | Session storage (encrypted via `Vault`) + login / logout / me HTTP calls to the cloud |
| `automate/server/api/auth.py` | `/api/auth/{me,login,logout}` proxy for the SPA |
| `automate/tools/registry.py` | `Tool.tier` field (`"free"` / `"pro"`) |
| `automate/agent/loop.py` | Pro-tier check before tool dispatch — emits `needs_pro_subscription` to the LLM if no session |
| `automate/frontend/index.html` + `app.js` | "autoMate Cloud" section in Settings; sign-in form when configured |
| `docs/cloud.md` | This file |

The boundary is set by **one environment variable**:

```bash
AUTOMATE_CLOUD_URL=https://cloud.automate.dev
```

- Unset (default): all cloud paths return cleanly.
  `/api/auth/me` returns `{logged_in: false, cloud_configured: false}`.
  Pro-tier tools tell the LLM to ask the user to sign in. UI shows
  "Cloud sync coming soon".
- Set: the client treats it as the base URL of an autoMate-Cloud
  server. POSTs `/api/auth/login` etc. expecting a JSON token back.

## Cloud server contract (what `automate-cloud` will implement)

Minimal API surface this open-source client expects:

```
POST /api/auth/login
  Request:  {"email": "...", "password": "..."}
  Response: {"token": "...", "tier": "free"|"pro", "expires_at": 1234567890}
  Errors:   401 {"error": "..."}

POST /api/auth/logout
  Header:   Authorization: Bearer <token>
  Response: {"ok": true}

GET /api/auth/me            (called via the proxy, optional)
  Header:   Authorization: Bearer <token>
  Response: {"email": "...", "tier": "..."}
```

That's it for v4.4. Future endpoints — sync, transcription, file
upload — will be added as we ship the corresponding client features.

## Self-hosting

If you don't trust autoMate-the-company (which doesn't exist yet) to
host your data, you have three honest paths:

1. **Don't sign in** — the open-source client gives you all the free
   features (notes, files, reminders, agent, bots, integrations,
   browser extension, MCP server, etc.) without a cloud at all.
2. **Run your own cloud** — implement the contract above (it's not
   complicated; ~500 lines of FastAPI + SQLite + S3 will do it) and
   set `AUTOMATE_CLOUD_URL` to point at it.
3. **Wait for the official open-source reference cloud** — we may
   release one for self-hosters, similar to how Standard Notes
   shipped a free Standard File server alongside its paid tier.
   No timeline yet.

## What's specifically NOT in this repo

These will be in the closed-source `automate-cloud` repo when that
project starts:

- Account registration + email verification
- Password reset / recovery
- Subscription billing (Stripe)
- Cloud blob storage (S3 + per-user quotas)
- Audio transcription relay (paid Whisper/Tencent ASR API costs)
- Public-content extraction (公众号 / Twitter / etc.)
- Sync conflict resolution (vector clocks)
- Multi-device sync API
- Push gateway for reminders that fire when no laptop is online

They're closed-source for the moat reasons above. The client
endpoints that talk to them will land in this repo as we ship each
feature.

## A word on forks

If you fork this repo, change the cloud URL, and run a competing
service: that's allowed. The license is permissive. We'd appreciate
attribution but won't sue you.

What we will do is keep building the official cloud, keep shipping
the open-source client, and let the brand + ops + free-quota story
do the work.
