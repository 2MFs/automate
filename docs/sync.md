# Sync — autoMate's "smart NAS" model

> Inspired by SiYuan Notes' device + sync architecture. Each install is a
> standalone "drive"; sync is a separate, opt-in concern.

## Mental model

autoMate is **a smart NAS for AI**: a warehouse the user owns, that any
LLM can plug into. A NAS doesn't force you to be at home to access it —
that's what sync (or remote access) is for.

Three deployment shapes, all interoperable:

```
   ┌─ Phone PWA ───────┐                    ┌─ Laptop hub ─────┐
   │ local IndexedDB   │  ◀─ sync ─▶        │ SQLite + tools   │
   └───────────────────┘                    └──────────────────┘
            ▲                                        ▲
            │                                        │
            └────────────── (opt) cloud relay ───────┘
                            paid, encrypted, hosted
```

| Shape | Storage | When useful |
|---|---|---|
| **Phone-only** | IndexedDB on the device | "I just want to take notes on my phone" |
| **Laptop hub** | SQLite + filesystem | "I want the full warehouse with tools, files, reminders" |
| **Phone + hub, synced** | Both, reconciled | "Notes on phone, big files + tools on laptop, both stay in sync" |
| **+ cloud relay** | Both + encrypted blob storage | "Same as above but accessible from anywhere, no port-forwarding" |

The first two work today. The third works in v4.2.0 for **notes + memory**
(via the "Sync & connect" banner). The fourth is on the roadmap.

## v4.2.0 today

When the SPA loads and `/api/health` doesn't answer, it drops into
**local mode**:

- Notes and memory are stored in IndexedDB (per-origin)
- Files, reminders, models, tools, and Bots tabs show a "needs hub"
  card; nothing's pretending to work
- A yellow banner across the top has a hub-URL input + "Sync & connect"

Clicking **Sync & connect**:

1. Pushes every local note + memory item to the hub at the URL you
   typed. The hub upserts (last-write-wins by `updated_at`).
2. Pulls the hub's notes + memory back to IndexedDB, merging by
   `updated_at` (newer wins).
3. Saves the hub URL in `localStorage` so the SPA flips to **connected
   mode** on the next reload — from then on, every API call goes to that
   hub.

No conflict resolution beyond last-write-wins yet. For v4.2 most users
have one writer at a time; a real CRDT or vector-clock layer can come in
v5.

## Free vs paid

```
┌──────────────────────────────────────────────────────────────┐
│  Free                                                         │
│  ───                                                          │
│  · Local-only on every device.                                │
│  · Manual sync via the "Sync & connect" banner.               │
│  · Self-host a relay (docs/relay.md) for WAN access.          │
│  · You own the bytes; we never see them.                      │
│                                                               │
│  Paid (planned)                                               │
│  ─────                                                        │
│  · Account-based hosted relay (no port-forwarding required).  │
│  · End-to-end encrypted blob storage for the file vault.      │
│  · Push notifications for reminders, even when no laptop is   │
│    online (relay-side scheduler).                             │
│  · One subscription covers all your devices.                  │
└──────────────────────────────────────────────────────────────┘
```

The free tier is genuinely useful — local + manual sync is what most
single-user setups actually need. The paid tier's pitch is "I don't want
to think about ports, my laptop is asleep, I want a phone reminder when
I'm out".

## Roadmap

| Feature | Status |
|---|---|
| Local notes + memory in IndexedDB | ✅ v4.2.0 |
| Sync notes + memory to a hub | ✅ v4.2.0 (last-write-wins) |
| File vault on phone (IndexedDB blobs ≤ 100 MB) | ◯ v4.3 |
| Reminder local fallback (in-app while open) | ◯ v4.3 |
| Conflict resolution (vector clocks / CRDTs) | ◯ v4.4 |
| End-to-end encrypted sync payloads | ◯ v4.4 |
| Hosted relay (free tier with rate limit) | ◯ v5.0 |
| Hosted relay (paid + cloud blob storage + push) | ◯ v5.0 |

## Privacy

- Local mode: data lives in your browser's IndexedDB; never leaves the
  device unless you initiate sync.
- Connected mode: SPA → hub over HTTP. Bind the hub to `127.0.0.1` and
  it's localhost-only; bind to `0.0.0.0` and your LAN can reach it
  (don't do that on coffee-shop WiFi).
- Self-hosted relay: same as connected mode, but the relay is a server
  you control.
- Hosted relay (when it exists): tunnel terminates at our edge, but the
  payload is end-to-end encrypted (planned for v4.4 before launch). We
  see the metadata to route, never the content.
