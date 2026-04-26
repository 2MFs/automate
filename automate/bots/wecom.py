"""企业微信 (WeCom) — webhook + active push.

企业微信 has a friendlier integration story than 公众号:
- 主动消息 via /cgi-bin/message/send (no 5s limit, can post any time)
- Self-built apps support full bidirectional integration
- B-end audience (businesses); harder to monetise as C-end but stable

Setup:
1. work.weixin.qq.com → 应用管理 → 自建应用
2. Note the corp_id, agent_id, and app secret
3. In the app's 接收消息 panel, point the URL at
   ``https://<your-public-host>/api/bots/wecom/webhook``
4. We use the ``Token`` and ``EncodingAESKey`` here for handshake.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .base import Bot, BotMeta

log = logging.getLogger("automate.bots.wecom")

META = BotMeta(
    id="wecom",
    label="企业微信 (WeCom)",
    description="Self-built app on work.weixin.qq.com. Active push, no 5s reply limit. Best for internal/B-end use.",
    docs_url="https://developer.work.weixin.qq.com/document/path/90664",
    config_fields=[
        {"name": "corp_id",          "label": "企业 ID (CorpID)",           "kind": "string",   "required": True},
        {"name": "agent_id",         "label": "应用 AgentID",              "kind": "string",   "required": True},
        {"name": "secret",           "label": "应用 Secret",               "kind": "password", "required": True},
        {"name": "token",            "label": "Token",                    "kind": "string",   "required": True},
        {"name": "encoding_aes_key", "label": "EncodingAESKey",           "kind": "password", "required": False},
    ],
)


class WeComBot(Bot):
    kind = "wecom"

    def __init__(self, *, config: dict, agent):
        self.config = config
        self.agent = agent
        self._status = "ready"
        self._access_token = ""
        self._access_token_expires = 0.0

    @property
    def status(self) -> str:
        return self._status

    def start(self) -> None:
        self._status = "ready"

    def stop(self) -> None:
        self._status = "stopped"

    # ---- handshake ----

    def verify_handshake(self, *, signature: str, timestamp: str, nonce: str, echostr: str | None = None) -> bool:
        token = (self.config.get("token") or "").strip()
        if not token:
            return False
        check = "".join(sorted([token, timestamp, nonce] + ([echostr] if echostr else [])))
        return hashlib.sha1(check.encode()).hexdigest() == signature

    # ---- inbound ----

    def handle_inbound(self, raw_xml: bytes) -> str:
        try:
            root = ET.fromstring(raw_xml)
            from_user = (root.findtext("FromUserName") or "").strip()
            content = (root.findtext("Content") or "").strip()
        except Exception as e:  # noqa: BLE001
            log.warning("malformed wecom payload: %s", e)
            return ""
        if not content:
            return ""

        log.info("[wecom] from %s: %s", from_user, content[:80])
        # WeCom doesn't enforce a strict 5s window, but we still answer fast
        # and use 主动消息 for anything bigger / async.
        try:
            answer = self.agent(content) if self.agent else "(agent not wired)"
        except Exception as e:  # noqa: BLE001
            answer = f"⚠ {type(e).__name__}: {e}"

        # Best-effort: try to deliver via 主动消息 immediately so we don't
        # have to fit inside the response XML.
        try:
            self.send_text(from_user, answer)
            return ""    # respond with empty body; user already got the message
        except Exception as e:  # noqa: BLE001
            log.warning("active push failed, falling back to passive reply: %s", e)
            return f"<xml><MsgType>text</MsgType><Content><![CDATA[{answer[:1500]}]]></Content></xml>"

    # ---- access token + active push ----

    def _ensure_access_token(self) -> str:
        if self._access_token and time.time() < self._access_token_expires - 60:
            return self._access_token
        params = urllib.parse.urlencode({
            "corpid": self.config["corp_id"],
            "corpsecret": self.config["secret"],
        })
        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?{params}"
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode())
        if data.get("errcode"):
            raise RuntimeError(f"wecom gettoken failed: {data}")
        self._access_token = data["access_token"]
        self._access_token_expires = time.time() + int(data.get("expires_in", 7200))
        return self._access_token

    def send_text(self, to_user: str, text: str) -> dict:
        token = self._ensure_access_token()
        body = {
            "touser": to_user,
            "msgtype": "text",
            "agentid": int(self.config["agent_id"]),
            "text": {"content": text[:2048]},
        }
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        if data.get("errcode"):
            raise RuntimeError(f"wecom send failed: {data}")
        return data
