"""FastAPI factory."""
from __future__ import annotations

import contextlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .. import channels as C
from ..version import __version__
from .api import (
    agent, audio, auth, bots, channels as channels_api, execute,
    extension, files, integrations, memory, models, notes, oauth, push,
    reminders, sessions, system, tools as tools_api,
)
from .state import AppState, build_state


def create_app() -> FastAPI:
    state = build_state()

    # v4.5.7: build the MCP-over-HTTP app once at startup. Its
    # session_manager needs to live inside the FastAPI lifespan so
    # streaming responses don't get cut off.
    try:
        from .mcp_bridge import build_http_app
        mcp_app, mcp_session = build_http_app(state)
    except SystemExit:
        # mcp[cli] not installed — skip the HTTP MCP mount silently.
        mcp_app, mcp_session = None, None

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        if mcp_session is not None:
            async with mcp_session.run():
                yield
        else:
            yield

    app = FastAPI(
        title="autoMate", version=__version__,
        description="A smart NAS for AI — notes, files, reminders, memory, tools. Plug in any LLM via MCP / HTTP / bridge.",
        lifespan=lifespan,
    )

    app.state.app_state = state

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system.router,        prefix="/api")
    app.include_router(models.router,        prefix="/api")
    app.include_router(tools_api.router,     prefix="/api")
    app.include_router(integrations.router,  prefix="/api")
    app.include_router(agent.router,         prefix="/api")
    app.include_router(execute.router,       prefix="/api")
    app.include_router(sessions.router,      prefix="/api")
    app.include_router(extension.router,     prefix="/api")
    # v5: personal-infra
    app.include_router(notes.router,         prefix="/api")
    app.include_router(files.router,         prefix="/api")
    app.include_router(reminders.router,     prefix="/api")
    app.include_router(memory.router,        prefix="/api")
    app.include_router(push.router,          prefix="/api")
    app.include_router(bots.router,          prefix="/api")
    app.include_router(auth.router,          prefix="/api")
    app.include_router(audio.router,         prefix="/api")
    app.include_router(channels_api.router,  prefix="/api")
    app.include_router(oauth.router)  # /oauth/<id>/callback (no /api prefix)

    # v4.5.7: MCP-over-HTTP mount, Bearer-protected. OpenClaw / Cursor /
    # any MCP client running on a different machine talks autoMate's
    # tools through this single endpoint.
    if mcp_app is not None:
        app.mount("/mcp", _BearerProtect(mcp_app, state.db))

    # Mount the static SPA last so /api/* and /mcp still win.
    frontend = Path(__file__).resolve().parent.parent / "frontend"
    if frontend.exists():
        app.mount("/", StaticFiles(directory=str(frontend), html=True), name="frontend")

    return app


class _BearerProtect:
    """Tiny ASGI wrapper that requires a Bearer token equal to the
    channels bridge token before forwarding to the inner app."""
    def __init__(self, inner, db):
        self.inner = inner
        self.db = db

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.inner(scope, receive, send)
            return
        # Mount strips the "/mcp" prefix; bare "/mcp" arrives as path="".
        # Redirect to "/mcp/" so MCP clients that drop the trailing slash
        # don't hit a confusing 405.
        if scope.get("path", "") == "":
            await _redirect(send, "/mcp/")
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            await _reject(send, 401, "missing Bearer token")
            return
        if not C.verify_token(self.db, auth.split(" ", 1)[1].strip()):
            await _reject(send, 401, "invalid token")
            return
        await self.inner(scope, receive, send)


async def _redirect(send, location: str) -> None:
    await send({"type": "http.response.start", "status": 307,
                "headers": [(b"location", location.encode()),
                            (b"content-length", b"0")]})
    await send({"type": "http.response.body", "body": b""})


async def _reject(send, status: int, detail: str) -> None:
    body = (b'{"error":"' + detail.encode() + b'"}')
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


def get_state(app: FastAPI) -> AppState:
    return app.state.app_state
