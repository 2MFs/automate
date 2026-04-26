"""Bot framework — IM channels that wrap the agent loop.

The hub already exposes the agent over HTTP and MCP. Bots are a *third*
shape: they consume messages from a chat platform (Telegram, 微信公众号,
企业微信, 个人微信), feed them to the agent, and post the answer back.

Each bot is a small adapter. Common shape:

    class MyBot(Bot):
        kind = "telegram"
        def start(self) -> None: ...
        def stop(self) -> None: ...
        def handle_inbound(self, raw) -> Reply: ...
"""

from .base import Bot, BotMeta, BotReply
from .manager import BotManager

__all__ = ["Bot", "BotMeta", "BotReply", "BotManager"]
