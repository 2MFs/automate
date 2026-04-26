"""个人微信 — placeholder + risk warning.

Personal-WeChat protocols (itchat / wechaty / 各种 hook) all run against
unofficial endpoints and will get the linked WeChat account banned with
varying frequency. Tencent does not provide an official developer
interface for personal accounts.

For v1 this module exists so the bot manager has a uniform shape for the
UI, but it doesn't actually start anything. When you're ready to invest
in this channel, drop in a wechaty/itchat backend here.
"""
from __future__ import annotations

import logging

from .base import Bot, BotMeta

log = logging.getLogger("automate.bots.wechat_personal")

META = BotMeta(
    id="wechat_personal",
    label="个人微信",
    description="Personal WeChat (NOT officially supported by Tencent). High account-ban risk. Defer until we settle on a protocol stack.",
    docs_url="https://github.com/wechaty/wechaty",
    risks="非官方协议;封号风险高;不建议用主账号绑定。",
    config_fields=[
        {"name": "backend", "label": "Backend (wechaty / itchat / padlocal)", "kind": "string", "required": False,
         "hint": "Coming in a later release. For now this entry is a stub."},
    ],
)


class WeChatPersonalBot(Bot):
    kind = "wechat_personal"

    def __init__(self, *, config: dict, agent):
        self.config = config
        self.agent = agent
        self._status = "stopped"

    @property
    def status(self) -> str:
        return self._status

    def start(self) -> None:
        # Intentional no-op — see module docstring.
        self._status = "not_implemented"
        log.warning("个人微信 backend not implemented yet — see automate/bots/wechat_personal.py")

    def stop(self) -> None:
        self._status = "stopped"
