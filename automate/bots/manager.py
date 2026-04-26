"""Bot manager — owns lifecycle of each bot kind, persists config, dispatches messages."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from ..agent import AgentLoop
from ..store import Database
from .base import Bot, BotMeta
from .telegram import META as TELEGRAM_META, TelegramBot
from .wechat_oa import META as OA_META, WeChatOABot
from .wecom import META as WECOM_META, WeComBot
from .wechat_personal import META as WX_PERSONAL_META, WeChatPersonalBot

log = logging.getLogger("automate.bots.manager")


CATALOG: dict[str, tuple[BotMeta, type[Bot]]] = {
    TELEGRAM_META.id:    (TELEGRAM_META,    TelegramBot),
    OA_META.id:          (OA_META,          WeChatOABot),
    WECOM_META.id:       (WECOM_META,       WeComBot),
    WX_PERSONAL_META.id: (WX_PERSONAL_META, WeChatPersonalBot),
}


class BotManager:
    def __init__(self, *, db: Database, agent: AgentLoop):
        self.db = db
        self.agent = agent
        self._instances: dict[str, Bot] = {}

    def _agent_run(self, prompt: str) -> str:
        """Bridge from a bot's plain-text input to the agent loop's reply."""
        try:
            result = self.agent.run(prompt, source="bot")
            return result.final or "(no reply)"
        except RuntimeError as e:
            return f"⚠ {e}"

    # ---- discovery ----

    def list_kinds(self) -> list[dict]:
        """Static catalog for the UI."""
        return [
            {
                "id": meta.id, "label": meta.label,
                "description": meta.description,
                "config_fields": meta.config_fields,
                "risks": meta.risks, "docs_url": meta.docs_url,
            }
            for meta, _cls in CATALOG.values()
        ]

    def list_instances(self) -> list[dict]:
        """Persisted bot rows + live status."""
        rows = self.db.fetchall("SELECT * FROM bots ORDER BY id") or []
        out = []
        for r in rows:
            inst = self._instances.get(r["id"])
            out.append({
                "id": r["id"],
                "enabled": bool(r["enabled"]),
                "status": inst.status if inst else r["status"],
                "last_error": r.get("last_error") or (inst and inst.last_error) or "",
                "config_set": bool(r["config_enc"]),
                "updated_at": r["updated_at"],
            })
        return out

    def get_config(self, bot_id: str) -> dict:
        row = self.db.fetchone("SELECT config_enc FROM bots WHERE id = ?", (bot_id,))
        if not row or not row["config_enc"]:
            return {}
        try:
            return json.loads(self.db.vault.decrypt(row["config_enc"]))
        except Exception as e:  # noqa: BLE001
            log.warning("config decrypt failed for %s: %s", bot_id, e)
            return {}

    def save_config(self, bot_id: str, config: dict) -> None:
        if bot_id not in CATALOG:
            raise ValueError(f"unknown bot kind: {bot_id}")
        merged = self.get_config(bot_id)
        # Empty values mean "leave the existing one alone" — useful for password fields.
        for k, v in config.items():
            if v == "" or v is None:
                continue
            merged[k] = v
        enc = self.db.vault.encrypt(json.dumps(merged))
        self.db.execute(
            "INSERT INTO bots (id, enabled, config_enc, status, updated_at) VALUES (?, 0, ?, 'stopped', ?) "
            "ON CONFLICT(id) DO UPDATE SET config_enc = excluded.config_enc, updated_at = excluded.updated_at",
            (bot_id, enc, time.time()),
        )

    # ---- lifecycle ----

    def start(self, bot_id: str) -> dict:
        meta_cls = CATALOG.get(bot_id)
        if not meta_cls:
            raise ValueError(f"unknown bot: {bot_id}")
        _meta, cls = meta_cls
        cfg = self.get_config(bot_id)
        if not cfg:
            raise RuntimeError("no config saved yet — fill in the form first")
        # Stop any existing instance before starting a new one.
        old = self._instances.pop(bot_id, None)
        if old:
            try: old.stop()
            except Exception: pass  # noqa: BLE001
        instance = cls(config=cfg, agent=self._agent_run)
        try:
            instance.start()
        except Exception as e:  # noqa: BLE001
            self.db.execute(
                "UPDATE bots SET enabled=0, status='error', last_error=?, updated_at=? WHERE id=?",
                (str(e), time.time(), bot_id),
            )
            raise
        self._instances[bot_id] = instance
        self.db.execute(
            "UPDATE bots SET enabled=1, status=?, last_error=NULL, updated_at=? WHERE id=?",
            (instance.status, time.time(), bot_id),
        )
        return {"status": instance.status}

    def stop(self, bot_id: str) -> None:
        inst = self._instances.pop(bot_id, None)
        if inst:
            try: inst.stop()
            except Exception: pass  # noqa: BLE001
        self.db.execute(
            "UPDATE bots SET enabled=0, status='stopped', updated_at=? WHERE id=?",
            (time.time(), bot_id),
        )

    def get_instance(self, bot_id: str) -> Bot | None:
        return self._instances.get(bot_id)

    def restart_enabled(self) -> None:
        """Called at server startup — bring back bots that were running before shutdown."""
        rows = self.db.fetchall("SELECT id FROM bots WHERE enabled = 1") or []
        for r in rows:
            try:
                self.start(r["id"])
            except Exception as e:  # noqa: BLE001
                log.warning("could not auto-start bot %s: %s", r["id"], e)
