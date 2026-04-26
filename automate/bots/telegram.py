"""Telegram bot — long-poll based so it works from behind NAT.

No webhook URL needed. Just paste the token from BotFather, click Start,
chat with the bot. Outbound messages go via the standard ``sendMessage``
HTTP API.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request

from .base import Bot, BotMeta

log = logging.getLogger("automate.bots.telegram")

META = BotMeta(
    id="telegram",
    label="Telegram",
    description="Personal Telegram bot via long polling. No public URL needed — works from your laptop / NAS / Docker.",
    docs_url="https://core.telegram.org/bots/api",
    config_fields=[
        {"name": "bot_token", "label": "Bot token", "kind": "password", "required": True,
         "hint": "From @BotFather on Telegram. Looks like 1234:ABC..."},
    ],
)


class TelegramBot(Bot):
    kind = "telegram"

    def __init__(self, *, config: dict, agent):
        self.config = config
        self.agent = agent
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._offset = 0
        self._status = "stopped"
        self._last_error = ""

    @property
    def status(self) -> str:
        return self._status

    @property
    def last_error(self) -> str:
        return self._last_error

    def _api(self, method: str, params: dict | None = None) -> dict:
        token = self.config.get("bot_token", "").strip()
        if not token:
            raise RuntimeError("bot_token is empty")
        url = f"https://api.telegram.org/bot{token}/{method}"
        body = json.dumps(params or {}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=35) as r:
            return json.loads(r.read().decode())

    def start(self) -> None:
        if self._thread:
            return
        self._stop.clear()
        # Tiny self-test before we kick off the loop.
        try:
            me = self._api("getMe")
            if not me.get("ok"):
                raise RuntimeError(me.get("description", "getMe failed"))
            log.info("Telegram bot started: @%s", me["result"].get("username"))
            self._status = "running"
            self._last_error = ""
        except Exception as e:  # noqa: BLE001
            self._status = "error"
            self._last_error = str(e)
            raise
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="automate-tg-bot")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._status = "stopped"

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                resp = self._api("getUpdates", {"offset": self._offset, "timeout": 25})
                for update in resp.get("result", []):
                    self._offset = update["update_id"] + 1
                    msg = update.get("message")
                    if not msg or "text" not in msg:
                        continue
                    self._handle(msg)
            except Exception as e:  # noqa: BLE001
                log.warning("Telegram poll error: %s", e)
                self._last_error = str(e)
                # Back off briefly so a misconfigured token doesn't hammer the API.
                if self._stop.wait(5):
                    break

    def _handle(self, msg: dict) -> None:
        chat_id = msg["chat"]["id"]
        text = msg["text"].strip()
        if not text:
            return
        log.info("[telegram] from %s: %s", chat_id, text[:80])
        # Acknowledge receipt — give long agent runs feedback.
        try:
            self._api("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        except Exception:  # noqa: BLE001
            pass
        try:
            reply = self.agent(text) if self.agent else "(agent not wired)"
        except Exception as e:  # noqa: BLE001
            reply = f"⚠ {type(e).__name__}: {e}"
        # Telegram caps a single message at ~4096 chars — split if long.
        for chunk in _chunks(reply, 3500):
            try:
                self._api("sendMessage", {"chat_id": chat_id, "text": chunk})
            except Exception as e:  # noqa: BLE001
                log.warning("telegram sendMessage failed: %s", e)
                break


def _chunks(text: str, n: int):
    for i in range(0, len(text), n):
        yield text[i:i + n]
