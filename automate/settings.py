"""Filesystem layout, defaults, and runtime settings.

Everything autoMate writes lives under ``~/.automate`` so a fresh install is one
directory away. Override with the ``AUTOMATE_HOME`` env var for tests or
multi-profile setups.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _home() -> Path:
    raw = os.environ.get("AUTOMATE_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".automate"


@dataclass(frozen=True)
class Paths:
    home: Path
    db: Path
    secret_key: Path
    logs: Path
    scripts: Path
    sessions: Path
    cache: Path
    files: Path

    @classmethod
    def default(cls) -> "Paths":
        h = _home()
        return cls(
            home=h,
            db=h / "automate.db",
            secret_key=h / "secret.key",
            logs=h / "logs",
            scripts=h / "scripts",
            sessions=h / "sessions",
            cache=h / "cache",
            files=h / "files",
        )

    def ensure(self) -> None:
        for p in (self.home, self.logs, self.scripts, self.sessions, self.cache, self.files):
            p.mkdir(parents=True, exist_ok=True)


PATHS = Paths.default()


@dataclass(frozen=True)
class Server:
    host: str = os.environ.get("AUTOMATE_HOST", "127.0.0.1")
    port: int = int(os.environ.get("AUTOMATE_PORT", "8765"))
    open_browser: bool = os.environ.get("AUTOMATE_OPEN_BROWSER", "1") != "0"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


SERVER = Server()
