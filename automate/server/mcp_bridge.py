"""Re-export the tool registry as a FastMCP server.

So a Claude Desktop / Cursor / Cline / OpenClaw / Kimi / etc. instance can
mount autoMate as an MCP server and immediately get every shell / browser /
SaaS tool, plus a top-level ``automate`` tool that runs the full agent loop.

Two transports:
- ``serve_stdio()`` — for Claude Desktop and other clients that spawn the
  server as a child process.
- ``build_http_app(state)`` — returns a Starlette ASGI app for HTTP /
  Streamable-HTTP transport. Mounted at ``/mcp`` in the main FastAPI app
  (see ``app.py``) so OpenClaw on another machine can register autoMate
  as a tool source over the network.
"""
from __future__ import annotations

import json
from typing import Any


def _build_mcp(state):
    """Construct a FastMCP instance with all autoMate tools registered."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:
        raise SystemExit(
            "Install with: pip install 'autoMate[mcp]' (mcp[cli] required)"
        ) from e

    # streamable_http_path="/" so the user-facing endpoint is whatever
    # we mount the inner app at (we mount at "/mcp"). Without this, the
    # inner default of "/mcp" combines with our mount to yield "/mcp/mcp".
    mcp = FastMCP("autoMate", json_response=True, streamable_http_path="/")

    # 1) Top-level autonomous mode: NL prompt → agent loop.
    @mcp.tool()
    def automate(prompt: str) -> str:
        """Run an autoMate agent loop from a natural-language prompt.

        autoMate plans, picks tools, fills in parameters, executes, and returns
        the final answer. Best when the caller wants autoMate to figure out the
        steps. For specific operations (look up a note, read a file), the
        caller should pick the dedicated tool below directly."""
        try:
            result = state.agent.run(prompt, source="mcp")
        except RuntimeError as e:
            return f"autoMate error: {e}"
        return result.final or "(no final answer)"

    # 2) Direct tool invocation: surface every registered tool individually
    #    so OpenClaw's planner can pick search.find / files.read / etc. by
    #    name without going through autoMate's own loop.
    for tool in state.registry.all():
        _wrap_tool_for_mcp(mcp, tool)

    return mcp


def serve_stdio() -> None:
    from .state import build_state
    state = build_state()
    mcp = _build_mcp(state)
    mcp.run()


def build_http_app(state):
    """Return a Starlette ASGI app that speaks MCP over HTTP/SSE.

    Designed to be mounted at ``/mcp`` in the main FastAPI app via
    ``Mount("/mcp", app=...)``. The lifespan that runs the FastMCP
    session manager must be exported and merged into the parent app's
    lifespan — see ``app.py``."""
    mcp = _build_mcp(state)
    return mcp.streamable_http_app(), mcp.session_manager


def _wrap_tool_for_mcp(mcp, tool) -> None:
    """Register a registry Tool with FastMCP using a generic kwargs handler."""
    def handler(**kwargs: Any) -> str:  # noqa: ANN401
        try:
            result = tool.call(kwargs)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"error": f"{type(e).__name__}: {e}"})
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)

    handler.__name__ = tool.name.replace(".", "_").replace("-", "_")
    handler.__doc__ = tool.description
    # FastMCP infers schema from the wrapper's signature; we accept **kwargs
    # and rely on the LLM-side schema (provided by the registry). Most clients
    # accept this; if a client requires strict schema, we'd codegen typed
    # wrappers.
    mcp.tool()(handler)
