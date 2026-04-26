"""FastAPI factory."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..version import __version__
from .api import (
    agent, auth, bots, connect, execute, extension, files, integrations,
    memory, models, notes, oauth, push, reminders, sessions, system,
    tools as tools_api,
)
from .state import AppState, build_state


def create_app() -> FastAPI:
    state = build_state()
    app = FastAPI(title="autoMate", version=__version__,
                  description="A smart NAS for AI — notes, files, reminders, memory, tools. Plug in any LLM via MCP / HTTP / bridge.")

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
    app.include_router(connect.router,       prefix="/api")
    # v5: personal-infra
    app.include_router(notes.router,         prefix="/api")
    app.include_router(files.router,         prefix="/api")
    app.include_router(reminders.router,     prefix="/api")
    app.include_router(memory.router,        prefix="/api")
    app.include_router(push.router,          prefix="/api")
    app.include_router(bots.router,          prefix="/api")
    app.include_router(auth.router,          prefix="/api")
    app.include_router(oauth.router)  # /oauth/<id>/callback (no /api prefix)

    # Mount the static SPA last so /api/* still wins.
    frontend = Path(__file__).resolve().parent.parent / "frontend"
    if frontend.exists():
        app.mount("/", StaticFiles(directory=str(frontend), html=True), name="frontend")

    return app


def get_state(app: FastAPI) -> AppState:
    return app.state.app_state
