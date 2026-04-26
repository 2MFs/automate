"""Generic channel inbox — bridge IM messages into the agent loop.

Architecture (v4.5.6, "Path A"): autoMate doesn't reimplement WeChat /
WhatsApp / Telegram protocols. An external gateway (OpenClaw, your own
script, n8n, whatever) handles the chat platform's quirks; it speaks
to autoMate over a single tiny HTTP contract:

    POST /api/channels/inbox
    Authorization: Bearer <bridge_token>
    {
        "channel":  "wechat",          # any string
        "user_id":  "wxid_abc123",     # opaque, stable per IM user
        "text":     "find my Tokyo notes",
        "context":  {...optional...}    # gateway-specific; passed through
    }

    -> 200 OK
    {
        "text":   "Found 1 note: 'Tokyo trip 2026'.",
        "events": [...optional run trace...]
    }

The gateway is responsible for: rendering the reply back to the user on
the chat platform, file/voice attachment uploads, group vs DM routing.
autoMate is responsible for: understanding the message, calling tools,
producing the answer.

Sessions are keyed by ``(channel, user_id)`` so the agent has memory
across messages from the same person on the same platform — without
the gateway needing to track anything.
"""
from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass, field

from .agent.loop import AgentLoop
from .agent.prompts import SYSTEM_PROMPT
from .store import Database

log = logging.getLogger("automate.channels")

TOKEN_KEY = "channels.bridge_token"


# ---------- token ---------------------------------------------------------

def get_or_create_token(db: Database) -> str:
    """Return the bridge auth token, generating one on first call.

    Stored alongside other app settings (Fernet-protected at the
    sqlite-file level, but the value itself is plaintext — gateways
    need to read it back to send it as a Bearer header)."""
    existing = db.get_setting(TOKEN_KEY)
    if existing:
        return existing
    token = secrets.token_urlsafe(32)
    db.set_setting(TOKEN_KEY, token)
    return token


def regenerate_token(db: Database) -> str:
    token = secrets.token_urlsafe(32)
    db.set_setting(TOKEN_KEY, token)
    return token


def verify_token(db: Database, candidate: str) -> bool:
    expected = db.get_setting(TOKEN_KEY)
    if not expected or not candidate:
        return False
    return secrets.compare_digest(expected, candidate)


# ---------- inbound message processing ------------------------------------

@dataclass
class InboundMessage:
    channel: str
    user_id: str
    text: str
    context: dict = field(default_factory=dict)


@dataclass
class Reply:
    text: str
    run_id: str
    ms: int


def process_inbound(msg: InboundMessage, *, agent: AgentLoop) -> Reply:
    """Run a channel-bridged message through the agent loop. Synchronous;
    returns once the agent has a final answer.

    The ``source`` we hand to the agent loop encodes the channel +
    user, so traces in the runs table are searchable by who said what
    on which platform. The agent prompt is augmented with a short
    context line explaining where the message came from — the LLM
    needs to know it's talking through WeChat (terse + Chinese-likely)
    vs Slack (long-form OK) so it can adapt tone.
    """
    started = time.time()
    src = f"channel:{msg.channel}:{msg.user_id}"
    framed = (
        f"[message from user '{msg.user_id}' on {msg.channel}]\n\n"
        f"{msg.text.strip()}"
    )
    result = agent.run(framed, source=src)
    return Reply(
        text=(result.final or "").strip() or "(no reply produced)",
        run_id=result.id,
        ms=int((time.time() - started) * 1000),
    )
