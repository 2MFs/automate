# Channels — connect autoMate to OpenClaw / Claude / Cursor / etc.

> **v4.5.7:** the architecture is now: autoMate is **a tool source**.
> OpenClaw (or Claude Desktop, Cursor, Cline, ...) stays the agent;
> autoMate plugs in via MCP and gives that agent access to the
> user's notes, files, reminders, memory, audio transcription, and
> 30+ other tools. The agent decides when to call autoMate.
>
> This replaces the v4.5.6 "autoMate intercepts all messages"
> design, which conflated channel handling with reasoning. The
> v4.5.6 inbox endpoint is still shipped for non-MCP gateways
> (n8n, custom scripts) but is no longer the recommended path.

## Two ways to use autoMate

**1. As a tool inside another AI client** (the main path)

```
WeChat / Telegram / etc.       OpenClaw / Claude / Cursor
        ▼                              ▼
        └─── (channel plugin) ────►   agent ────► MCP ────► autoMate
                                                  │            │
                                                  ▼            ▼
                                           tools live      files / notes /
                                           there too       memory /
                                                           reminders / agent
```

The user talks to OpenClaw (or whatever client) on their preferred
chat platform. The agent in OpenClaw decides "this needs the user's
files / notes / schedule" and calls autoMate's tools. autoMate
returns the data; the agent composes the reply.

**2. autoMate's own web chat** (the lightweight path)

Open the autoMate hub URL in a browser. Use the built-in chat tab.
autoMate's own agent runs the loop — handy for quick queries
without an external client.

Both modes share the same backend. Tools, files, notes, memory, and
the agent loop are the same. Pick whichever entry point fits the
moment.

## Connecting in mode 1

Open **autoMate Settings → Connect to AI clients** and click
**"Copy install text (all clients)"**. You get a single markdown
blob with the URL + token already filled in, plus per-client
sections for OpenClaw, Claude Desktop, Cursor, Cline, and generic
MCP clients.

Three ways to use that text:

- **Read it yourself** and edit your client's config file by hand.
  Each section tells you the file path and exact JSON to add.
- **Paste it into another AI** ("Cursor, here's autoMate, set it up
  for me") — the text is written so an AI can read the section that
  matches its own client and edit the right config file.
- **For OpenClaw specifically**, paste into your OpenClaw config
  under `bundle-mcp` — the section spells it out.

After the client picks up the new server, it'll see all autoMate's
tools (`search.find`, `notes.read`, `files.list`, ...) plus a
top-level `automate` tool that runs autoMate's own agent loop on
demand.

## The MCP endpoint

```
POST {hub}/mcp/                       # note trailing slash
Authorization: Bearer {token}
Content-Type:  application/json
Accept:        application/json, text/event-stream
```

Standard streamable-HTTP MCP — initialize, then `tools/list` and
`tools/call`. autoMate exposes ~40 tools out of the box.

The token is the same Bearer token used by the v4.5.6 inbox
endpoint. Stored in the existing `settings` KV table; rotate via
**Settings → Channels → Regenerate**.

## The legacy HTTP inbox (v4.5.6)

For tools that don't speak MCP — n8n, Zapier, custom Python /
Node scripts, iOS Shortcuts — there's still a flat HTTP inbox:

```http
POST /api/channels/inbox
Authorization: Bearer <token>

{"channel": "wechat", "user_id": "wxid_x", "text": "find my notes"}

→ {"text": "...", "run_id": "...", "ms": 1842}
```

Kept around because it's strictly easier than MCP for non-AI
gateways. But for AI clients, MCP is cleaner.

## What about v4.5.6's "OpenClaw outbound webhook" plan?

That was the wrong direction. The honest take:
- OpenClaw is an agent.
- autoMate is also an agent (with its own LLM, memory, etc.).
- Two agents fighting over one message stream is a bad pattern.
- Treating autoMate as a *tool* that OpenClaw's agent calls when
  needed is the clean pattern. That's what v4.5.7 ships.

The v4.5.6 inbox endpoint isn't deleted — it still works for cases
where you genuinely want autoMate to be the only brain (a custom
Telegram bot that just wraps autoMate, no OpenClaw). But it's no
longer the highlighted path.

## Deprecation status of `automate/bots/`

The old per-platform bot adapters (`telegram.py`, `wechat_oa.py`,
`wecom.py`, `wechat_personal.py`) remain frozen. New deployments
should use OpenClaw + the MCP bridge above. The old code will be
removed once OpenClaw integration is proven in the wild.
