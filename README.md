# autoMate

> **Your AI's brain.** Notes · files · reminders · 30+ tools — your data,
> your machine. Bring any AI.

autoMate is the personal-infrastructure layer that sits behind whichever
AI you already use. Don't switch chat apps; switch what's behind them.

```
   ┌─ Claude Code ──┐                  ┌─ notes.*           ← survives sessions
   ├─ Cursor / Cline├──── MCP ────┐    ├─ files.*           ← your file vault
   ├─ Kimi K2 / GPT ├──── HTTP ───┤    ├─ reminders.*       ← push to your phone
   ├─ Ollama / web  ├──── bridge ─┤    ├─ memory.*          ← cross-session facts
   └─ your scripts  ┘             │    │
                                  ▼    ▼
                          ┌──────────────────┐    ┌─ shell · script · browser
                          │     autoMate     │ ── ┤  desktop · 31 SaaS APIs
                          │  (your machine)  │    └─ your real Chrome (extension)
                          └────────┬─────────┘
                                   ▼
                          ~/.automate/  · SQLite + Fernet
```

## What's actually different

Every AI chat tool has chat. Most can call tools. None of them remember
anything across vendors, store your files, ping your phone when something
matters, or expose all of that to **whatever** chat tool you happen to
open tomorrow.

| You do this in… | autoMate gives you… |
|---|---|
| Kimi web chat | A local hub Kimi calls into for tools, notes, files |
| Claude Code | Same hub, accessed via MCP |
| Cursor / Cline | Same hub, also via MCP |
| Local Ollama in terminal | A bridge script that Ollama can shell out to |
| Your phone PWA | The same data, in your pocket — plus reminders that push to you |

The data lives in `~/.automate/`. Your files, notes, reminders, and tool
credentials never leave the machine unless you opt in to the relay.

## Install

| Path | Get | When |
|---|---|---|
| `pip install 'automate-hub[full]'` | Python package | Have Python, want it small |
| Standalone binary (Win / macOS / Linux) | [Releases](https://github.com/yuruotong1/autoMate/releases/latest) | No Python, double-click |
| Docker | `docker run -p 8765:8765 ghcr.io/yuruotong1/automate:latest` | Headless box / NAS |
| Browser extension | [`extension/`](./extension/) | Drive your real Chrome |
| Android APK | [Releases](https://github.com/yuruotong1/autoMate/releases/latest) | Phone (TWA wrapper around the PWA) |
| iOS / "any phone" | Open the hub URL → Add to Home Screen | PWA, works on every phone |

After install:

```bash
automate          # double-click on Windows/macOS does the same thing
```

Browser opens to `http://127.0.0.1:8765`. The welcome wizard walks you
through picking a model and pasting a key. ~2 minutes.

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

The UI is a Progressive Web App. Two paths:

1. **Same WiFi** (free): on your laptop, run
   `automate serve --host 0.0.0.0`. Find the LAN IP. On your phone,
   browse to `http://<your-ip>:8765` → menu → **Add to Home Screen**.
2. **Anywhere** (with relay): your laptop dials out to a relay,
   the phone connects via the relay's HTTPS URL. See
   [docs/relay.md](./docs/relay.md). Hosted relay is on the roadmap;
   self-hosting is documented.

The phone is a controller; your laptop runs the actual tools (a phone
sandbox can't run shell or drive your real browser).

## What's in the box

**Personal data (v5, new)**
- `notes.*` — markdown documents with tags, search, pinning
- `files.*` — content-addressed blob vault, deduplication, multipart upload
- `reminders.*` — scheduler thread fires Web Push to your PWA
- `memory.*` — long-term key-value facts that any AI can read/write

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
│  ├─ oauth/                 # OAuth flows
│  ├─ store/                 # SQLite + Fernet vault
│  ├─ frontend/              # static SPA — PWA installable
│  ├─ notes.py · files.py · reminders.py · memory.py · push.py
│  ├─ relay.py               # reverse-tunnel client for the optional relay
│  └─ extension_bus.py       # bridge to the Chrome extension
├─ extension/                # Chrome MV3 extension (load unpacked)
├─ packaging/                # PyInstaller spec
├─ docs/relay.md             # relay protocol + self-host guide
├─ Dockerfile
└─ pyproject.toml
```

## Privacy & safety

- Server binds to `127.0.0.1`. Network access is opt-in (`--host 0.0.0.0`).
- API keys, OAuth tokens, push subscriptions: encrypted with Fernet,
  key at `~/.automate/secret.key` (chmod 600).
- LLM calls go directly from autoMate to the provider you chose. Nothing
  else sees them.
- `shell.exec` and `script.run` run with the autoMate process's full
  privileges. Treat it like any automation tool: only run prompts you'd
  run yourself.

## Status

v5.0 — personal-infra layer (notes / files / reminders / memory) with
Web Push to PWA. Multi-platform distribution: pip · standalone binary ·
Docker · Chrome extension · Android APK · iOS PWA. Relay protocol
specified, hosted relay roadmapped.

中文版: [README_CN.md](./README_CN.md)

## License

MIT.
