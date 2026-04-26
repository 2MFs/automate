"""Agent execution loop.

Standard tool-use loop: chat → tool calls → execute → feed results back → repeat
until the model stops calling tools or we hit ``max_steps``.

The loop emits :class:`RunEvent` objects through a callback so the WebSocket
endpoint can stream live progress to the browser without coupling agent logic
to any transport.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Callable, Iterable

from ..providers import ChatMessage, ProviderManager, ToolSpec
from ..providers.base import ToolCall
from ..store import Database
from ..tools import ToolRegistry
from .prompts import SYSTEM_PROMPT


@dataclass
class RunEvent:
    kind: str                          # 'thinking' | 'tool_call' | 'tool_result' | 'final' | 'error'
    payload: dict = field(default_factory=dict)


@dataclass
class RunResult:
    id: str
    final: str
    events: list[RunEvent]


EventSink = Callable[[RunEvent], None]


class AgentLoop:
    def __init__(self, *, db: Database, providers: ProviderManager,
                 registry: ToolRegistry, max_steps: int = 8):
        self.db = db
        self.providers = providers
        self.registry = registry
        self.max_steps = max_steps

    def _tool_specs(self, allowed: Iterable[str] | None = None) -> list[ToolSpec]:
        out: list[ToolSpec] = []
        for t in self.registry.all():
            if allowed is not None and t.name not in allowed:
                continue
            out.append(ToolSpec(name=t.name, description=t.description, parameters=t.parameters))
        return out

    def run(self, prompt: str, *, source: str = "web", model: str | None = None,
            on_event: EventSink | None = None,
            allowed_tools: Iterable[str] | None = None) -> RunResult:
        run_id = uuid.uuid4().hex
        self.db.create_run(id=run_id, source=source, prompt=prompt)
        events: list[RunEvent] = []

        def emit(ev: RunEvent) -> None:
            events.append(ev)
            self.db.append_trace(run_id, {"kind": ev.kind, "payload": ev.payload})
            if on_event:
                try:
                    on_event(ev)
                except Exception:  # noqa: BLE001 — don't let UI failures break the run
                    pass

        client = self.providers.client()
        active_model = model or self.providers.active_model() or ""
        tools = self._tool_specs(allowed_tools)

        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt),
        ]

        final_text = ""
        try:
            for step in range(self.max_steps):
                emit(RunEvent("thinking", {"step": step}))
                response = client.chat(messages, model=active_model, tools=tools)
                if response.content:
                    emit(RunEvent("message", {"text": response.content}))
                if not response.tool_calls:
                    final_text = response.content or ""
                    emit(RunEvent("final", {"text": final_text}))
                    break

                # Record assistant turn (with tool_calls) so the next round is consistent.
                messages.append(ChatMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                ))
                for tc in response.tool_calls:
                    self._dispatch(tc, messages, emit)
            else:
                final_text = "Stopped: reached max tool-use steps without a final answer."
                emit(RunEvent("final", {"text": final_text, "truncated": True}))

            self.db.finish_run(run_id, status="done", result=final_text)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            emit(RunEvent("error", {"message": err}))
            self.db.finish_run(run_id, status="error", result=err)
            raise

        return RunResult(id=run_id, final=final_text, events=events)

    def _dispatch(self, tc: ToolCall, messages: list[ChatMessage], emit: EventSink) -> None:
        emit(RunEvent("tool_call", {"id": tc.id, "name": tc.name, "args": tc.arguments}))
        tool = self.registry.get(tc.name)
        if not tool:
            result_text = json.dumps({"error": f"unknown tool: {tc.name}"})
        elif tool.tier == "pro" and not self._has_pro_session():
            # Paid-tier tool, user not signed in. Return a clean message
            # the LLM can relay instead of executing the call.
            result_text = json.dumps({
                "error": "needs_pro_subscription",
                "message": (
                    f"The tool '{tool.name}' requires a Pro subscription. "
                    "Tell the user they can sign in via Settings → autoMate Cloud."
                ),
            })
        else:
            try:
                result = tool.call(tc.arguments)
                result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)[:8000]
            except Exception as e:  # noqa: BLE001
                result_text = json.dumps({"error": f"{type(e).__name__}: {e}"})
        emit(RunEvent("tool_result", {"id": tc.id, "name": tc.name, "result": result_text}))
        messages.append(ChatMessage(role="tool", tool_call_id=tc.id, name=tc.name, content=result_text))

    def _has_pro_session(self) -> bool:
        """Check whether a Pro session exists. Falls open (no session) if
        the auth module isn't wired — keeps free tools working in early
        installs that don't have AUTOMATE_CLOUD_URL set."""
        try:
            from .. import auth
            return auth.get_session(self.db) is not None
        except Exception:  # noqa: BLE001
            return False
