"""Bind catalog specs + DB-stored credentials → live ProviderClient instances."""
from __future__ import annotations

from ..store import Database
from .anthropic import AnthropicClient
from .base import ProviderClient
from .catalog import CATALOG, get_spec
from .litellm import LiteLLMClient
from .openai_compat import OpenAICompatClient


class ProviderManager:
    def __init__(self, db: Database):
        self.db = db

    def seed_catalog(self) -> None:
        """Insert catalog rows so the UI can render them even before keys are set."""
        for spec in CATALOG:
            existing = self.db.get_provider(spec.id)
            if existing:
                continue
            self.db.upsert_provider(
                id=spec.id,
                display_name=spec.display_name,
                base_url=spec.base_url,
                api_key=None,
                default_model=spec.models[0] if spec.models else None,
                enabled=False,
                extra={
                    "region": spec.region,
                    "adapter": spec.adapter,
                    "docs_url": spec.docs_url,
                    "api_key_url": spec.api_key_url,
                    "models": list(spec.models),
                    "requires_key": spec.requires_key,
                    "notes": spec.notes,
                },
            )

    def active_provider_id(self) -> str | None:
        return self.db.get_setting("active_provider")

    def set_active_provider(self, provider_id: str, model: str | None = None) -> None:
        self.db.set_setting("active_provider", provider_id)
        if model:
            self.db.set_setting("active_model", model)

    def active_model(self) -> str | None:
        return self.db.get_setting("active_model")

    def client(self, provider_id: str | None = None) -> ProviderClient:
        pid = provider_id or self.active_provider_id()
        if not pid:
            raise RuntimeError("No active LLM provider. Configure one in the UI.")
        spec = get_spec(pid)
        row = self.db.get_provider(pid, decrypt=True)
        if not spec or not row:
            raise RuntimeError(f"Unknown provider: {pid}")
        if spec.requires_key and not row.get("api_key"):
            raise RuntimeError(f"Provider '{pid}' has no API key configured.")
        base_url = row.get("base_url") or spec.base_url
        if spec.adapter == "litellm":
            return LiteLLMClient(
                model=row.get("default_model") or "",
                api_key=row.get("api_key"),
                api_base=base_url or None,
            )
        if spec.adapter == "anthropic":
            return AnthropicClient(
                base_url=base_url,
                api_key=row["api_key"],
                default_model=row.get("default_model") or "",
            )
        return OpenAICompatClient(
            spec_id=spec.id,
            base_url=base_url,
            api_key=row.get("api_key"),
            default_model=row.get("default_model") or "",
        )
