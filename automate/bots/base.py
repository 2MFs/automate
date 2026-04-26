"""Bot abstract base + shared types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class BotMeta:
    """Static description of a bot kind — surfaced in the UI."""
    id: str                     # 'telegram', 'wechat_oa', 'wecom', 'wechat_personal'
    label: str                  # 'Telegram'
    description: str
    config_fields: list[dict]   # JSON-Schema-ish: [{name, label, kind: 'string'|'password', required}]
    risks: str = ""             # e.g. 个人微信 封号风险
    docs_url: str = ""


@dataclass
class BotReply:
    """What an inbound message handler returns."""
    text: str = ""
    chat_id: str | int | None = None    # for bots that need to know where to reply


# Type alias for the agent dispatcher a bot calls
AgentHandler = Callable[[str], str]


class Bot(ABC):
    """Lifecycle + message-handling contract."""

    kind: str = ""                  # subclasses set this
    config: dict = {}
    agent: AgentHandler | None = None

    @abstractmethod
    def start(self) -> None:
        """Begin receiving messages (long-poll thread, webhook handler, etc.)."""

    @abstractmethod
    def stop(self) -> None:
        """Stop cleanly."""

    @property
    def status(self) -> str:
        return "stopped"
