# autoMate

> **A smart NAS for AI.** Your warehouse: notes · files · reminders ·
> memory · 30+ tools. Plug any LLM in. We don't make the chat — we make
> the storage and tool library behind it.

```
   ┌─ Claude Code ──┐                    ┌─ notes / memory ──── survives every chat
   ├─ Cursor / Cline├──── MCP ────┐      ├─ files ──────────── your file vault
   ├─ Kimi K2 / GPT ├──── HTTP ───┤      ├─ reminders ──────── push to your phone
   ├─ Ollama / web  ├──── bridge ─┤      ├─ memory ─────────── cross-session facts
   └─ your scripts  ┘             │      │
                                  ▼      ▼
                          ┌──────────────────┐    ┌─ shell · script · browser
                          │     autoMate     │ ── ┤  desktop · 31 SaaS APIs
                          │  (your machine)  │    └─ your real Chrome (extension)
                          └────────┬─────────┘
                                   ▼
                          ~/.automate/  · SQLite + Fernet
```

## What's the deal

Every AI vendor wants to be your chat tool. Most can call tools.
**None of them remember anything across vendors, store your files, or
ping your phone when something matters.**

autoMate is the layer behind the chat: a warehouse you own, with a
short snippet you paste into whatever AI you already use. From now on,
**that AI** can write into your notes, drop files, schedule reminders,
and call your real-world tools — and tomorrow's chat tool can read all
of it back the same way.

| You're using… | autoMate gives that AI… |
|---|---|
| Kimi web chat / ChatGPT | A local hub it calls into for tools, notes, files |
| Claude Code | Same hub, accessed via MCP |
| Cursor / Cline | Same hub, also via MCP |
| Local Ollama in terminal | A bridge script that Ollama can shell out to |
| Your phone (APK / PWA) | Your data in your pocket — even when the laptop is off |

## Two levels of "running it"

| Level | Storage | Best for |
|---|---|---|
| **Local-only** (phone APK / PWA) | IndexedDB on the device | Quick notes, while away from the laptop |
| **Hub** (laptop / NAS / Docker) | SQLite + filesystem + 30+ tools | The full warehouse: tools, files, push reminders |

Sync between them is opt-in. See [docs/sync.md](./docs/sync.md).

## Install

| Path | Get | When |
|---|---|---|
| `pip install 'automate-hub[full]'` | Python package | Have Python, want it small |
| Standalone binary (Win / macOS / Linux) | [Releases](https://github.com/yuruotong1/autoMate/releases/latest) | No Python, double-click |
| Docker | `docker run -p 8765:8765 ghcr.io/yuruotong1/automate:latest` | Headless box / NAS |
| Browser extension | [`extension/`](./extension/) | Drive your real Chrome |
| **Android APK** | [Releases](https://github.com/yuruotong1/autoMate/releases/latest) | Native phone app, works **standalone** in local mode |
| iOS / "any phone" | Open hub URL → Add to Home Screen | PWA, works on every phone |

After install:

```bash
automate          # double-click on Windows/macOS does the same thing
```

Browser opens to `http://127.0.0.1:8765`. The wizard walks you through
picking a model and pasting a key. ~2 minutes.

## Connect your other AI

Open the **Connect AI** tab, copy the snippet that matches your client.
Four modes:

| Mode      | Who it's for                                                |
|-----------|--------------------------------------------------------------|
| **MCP**   | Claude Code · Cursor · Cline · Kimi K2 · any MCP host        |
| **HTTP**  | ChatGPT custom GPTs · n8n · Make · your own scripts          |
| **Bridge**| Tool-less LLMs (basic Ollama, web chat) — relay shell script |
| **OpenAPI** | Agents that can self-discover schemas (`/openapi.json`)    |

That AI now has your hub's full tool catalog as native function calls.

## Use it on your phone

The phone is a **drive** that holds the lightweight bits (notes, memory)
and a **viewer** for the rest of the warehouse. Three install paths:

1. **Android APK** (real native app) — `autoMate-android.apk` from the
   release. Works **offline** for notes / memory. Tap the banner to sync
   with a hub on your laptop or a relay.
2. **PWA on Android** — open the hub URL in Chrome → Add to Home Screen.
3. **PWA on iOS** — open the hub URL in Safari → Share → Add to Home
   Screen. (Apple does not allow non-Store apps; PWA is the iOS path.
   Web Push works on iOS 16.4+.)

See [docs/mobile.md](./docs/mobile.md) for the install steps.

## What's in the box

**Personal data**
- `notes.*` — markdown documents with tags, search, pinning. Local on the
  device or on a hub.
- `files.*` — content-addressed blob vault, deduplication, multipart
  upload. Hub-only (phones don't have the storage budget).
- `reminders.*` — scheduler thread fires Web Push to your PWA. Hub-only.
- `memory.*` — long-term key-value facts that any AI can read/write.

**Local executors**
- `shell.*`, `script.*` (Python/Bash/Node), `desktop.*` (pyautogui)
- `browser.*` (Playwright, fresh Chromium tab)
- `bx.*` (your real browser via the [Chrome extension](./extension/README.md))

**SaaS integrations** — 31 platforms: GitHub · GitLab · Gitee · Notion ·
Slack · Linear · Jira · Confluence · Trello · Asana · Monday.com · HubSpot ·
Airtable · Stripe · Shopify · Telegram · Discord · MS Teams · Zoom ·
Twitter/X · SendGrid · Mailchimp · Twilio · Sentry · 飞书 · 钉钉 · 企业微信 ·
微信公众号 · 微博 · 语雀 · 高德地图.

**LLM providers** — 25 in the catalog: OpenAI · Anthropic · Gemini · xAI Grok ·
Mistral · Cohere · OpenRouter · Groq · Together · Fireworks · DeepInfra ·
DeepSeek · Moonshot Kimi · 通义 · 豆包 · GLM · 百川 · Yi · MiniMax · 阶跃 ·
混元 · 硅基流动 · Ollama · LM Studio · any OpenAI-compatible.

## Project layout

```
autoMate/
├─ automate/                 # the package
│  ├─ server/                # FastAPI app, REST + WS + MCP bridge
│  ├─ agent/                 # NL → tool-call loop
│  ├─ providers/             # LLM provider catalog + clients
│  ├─ tools/                 # shell · script · browser · desktop · bx
│  │                         # plus notes · files · reminders · memory
│  ├─ integrations/          # 31 SaaS connectors
│  ├─ frontend/              # static SPA — PWA installable
│  │  └─ local-store.js      # IndexedDB store for offline mode
│  ├─ notes.py · files.py · reminders.py · memory.py · push.py
│  ├─ relay.py               # reverse-tunnel client for the relay
│  └─ extension_bus.py       # bridge to the Chrome extension
├─ android/                  # native Android WebView app (APK)
├─ extension/                # Chrome MV3 extension
├─ packaging/                # PyInstaller spec
├─ docs/{relay,mobile,sync}.md
├─ Dockerfile
└─ pyproject.toml
```

## Privacy & safety

- Server binds to `127.0.0.1`. Network access is opt-in (`--host 0.0.0.0`).
- API keys, OAuth tokens, push subscriptions: encrypted with Fernet,
  key at `~/.automate/secret.key` (chmod 600).
- LLM calls go directly from autoMate to the provider you chose. Nothing
  else sees them.
- Phone in local mode: data is in IndexedDB on your device. Never
  leaves until you sync.

## Status

v4.2.0 — local-mode storage on phone (notes + memory in IndexedDB),
manual hub sync, native Android APK with bundled SPA. iOS via PWA.
Multi-platform distribution: pip · standalone binary · Docker · Chrome
extension · Android APK · iOS PWA.

中文版: [README_CN.md](./README_CN.md)

## License

MIT.
