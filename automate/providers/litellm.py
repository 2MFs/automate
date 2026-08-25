"""LiteLLM provider — routes to 100+ LLM providers via a unified interface.

Install: ``pip install automate-hub[litellm]``
"""
from __future__ import annotations

import json
from typing import Any, Iterator

from .base import ChatMessage, ChatResponse, ProviderClient, ToolCall, ToolSpec


class LiteLLMClient(ProviderClient):
    spec_id = "litellm"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        api_base: str | None = None,
        timeout: int = 120,
    ):
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self.timeout = timeout

    @staticmethod
    def _serialize_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            d: dict[str, Any] = {"role": m.role, "content": m.content or ""}
            if m.name:
                d["name"] = m.name
            if m.tool_calls:
                d["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in m.tool_calls
                ]
            if m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            out.append(d)
        return out

    def _build_kwargs(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": self._serialize_messages(messages),
            "temperature": temperature,
            "drop_params": True,
            "timeout": self.timeout,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if tools:
            kwargs["tools"] = [t.to_openai() for t in tools]
            kwargs["tool_choice"] = "auto"
        return kwargs

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        import litellm

        kwargs = self._build_kwargs(
            messages,
            model=model,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        response = litellm.completion(**kwargs)
        return self._parse_response(response)

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> Iterator[dict]:
        import litellm

        kwargs = self._build_kwargs(
            messages,
            model=model,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        kwargs["stream"] = True
        for chunk in litellm.completion(**kwargs):
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta:
                yield {
                    "delta": getattr(delta, "content", "") or "",
                    "tool_calls": getattr(delta, "tool_calls", []) or [],
                }

    @staticmethod
    def _parse_response(response: Any) -> ChatResponse:
        choice = response.choices[0].message
        content = getattr(choice, "content", "") or ""
        tool_calls: list[ToolCall] = []
        for tc in getattr(choice, "tool_calls", None) or []:
            fn = tc.function
            try:
                args = json.loads(fn.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": fn.arguments}
            tool_calls.append(ToolCall(id=tc.id, name=fn.name, arguments=args))
        return ChatResponse(content=content, tool_calls=tool_calls, raw=response)
