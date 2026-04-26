"""WeChat 公众号 (Subscription Account) — webhook-style.

公众号 only supports passive replies (we have ~5s after WeChat POSTs us
the message to respond with the reply XML). Long operations use 客服消息
sent in a follow-up call. For v1 we cap responses at ~4s and fall back
to "正在处理…" + async push.

Setup (one-time, on the user side):
1. Apply for a 公众号 ("订阅号" or "服务号") at mp.weixin.qq.com
2. In 开发 → 基本配置, set the URL to ``https://<your-public-host>/api/bots/wechat_oa/webhook``
   and the Token to whatever you save here. autoMate will validate the
   GET handshake automatically.
3. The hub MUST be reachable from the public internet — use the relay,
   ngrok, Cloudflare Tunnel, or a self-hosted reverse proxy.
"""
from __future__ import annotations

import hashlib
import logging
import time
import xml.etree.ElementTree as ET
from typing import Any

from .base import Bot, BotMeta

log = logging.getLogger("automate.bots.wechat_oa")

META = BotMeta(
    id="wechat_oa",
    label="微信公众号",
    description="Subscription / Service account on mp.weixin.qq.com. Massive C-end reach, but passive-reply only. Needs a public callback URL.",
    docs_url="https://developers.weixin.qq.com/doc/offiaccount/Basic_Information/Access_Overview.html",
    config_fields=[
        {"name": "token",         "label": "Token (you choose)",                  "kind": "string",   "required": True,
         "hint": "Pick any string. Paste the same value into the 公众号 backend → 开发 → 基本配置."},
        {"name": "app_id",        "label": "AppID",                               "kind": "string",   "required": True},
        {"name": "app_secret",    "label": "AppSecret",                           "kind": "password", "required": True},
        {"name": "encoding_aes_key","label": "EncodingAESKey (optional, for safe mode)", "kind": "password", "required": False},
    ],
)


class WeChatOABot(Bot):
    kind = "wechat_oa"

    def __init__(self, *, config: dict, agent):
        self.config = config
        self.agent = agent
        self._status = "ready"

    @property
    def status(self) -> str:
        return self._status

    def start(self) -> None:
        # Webhook bots have no background loop — they wait for inbound HTTP.
        # We just mark ourselves "ready". The actual handler lives on the
        # FastAPI route /api/bots/wechat_oa/webhook.
        self._status = "ready"

    def stop(self) -> None:
        self._status = "stopped"

    # ---- handshake (GET) ----

    def verify_handshake(self, *, signature: str, timestamp: str, nonce: str) -> bool:
        token = (self.config.get("token") or "").strip()
        if not token:
            return False
        check = "".join(sorted([token, timestamp, nonce]))
        return hashlib.sha1(check.encode()).hexdigest() == signature

    # ---- inbound message (POST XML) ----

    def handle_inbound(self, raw_xml: bytes) -> str:
        try:
            root = ET.fromstring(raw_xml)
            from_user = (root.findtext("FromUserName") or "").strip()
            to_user = (root.findtext("ToUserName") or "").strip()
            msg_type = (root.findtext("MsgType") or "").strip()
            content = (root.findtext("Content") or "").strip()
        except Exception as e:  # noqa: BLE001
            log.warning("malformed wechat_oa payload: %s", e)
            return ""

        if msg_type != "text" or not content:
            return self._make_reply(to_user, from_user, "目前只支持文本消息哦。")

        log.info("[wechat_oa] from %s: %s", from_user, content[:80])
        try:
            answer = self.agent(content) if self.agent else "(agent not wired)"
        except Exception as e:  # noqa: BLE001
            answer = f"⚠ {type(e).__name__}: {e}"

        # 公众号 5s soft limit — truncate long replies; full text gets pushed
        # via 客服消息 in a follow-up (TODO).
        if len(answer) > 1800:
            answer = answer[:1800] + "…\n(后续内容稍后通过客服消息发送)"
        return self._make_reply(to_user, from_user, answer)

    def _make_reply(self, from_user: str, to_user: str, content: str) -> str:
        return (
            "<xml>"
            f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
            f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
            f"<CreateTime>{int(time.time())}</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            f"<Content><![CDATA[{content}]]></Content>"
            "</xml>"
        )
