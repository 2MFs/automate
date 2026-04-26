from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query

from ... import files as F
from ...extension_bus import bus
from ...settings import PATHS
from ...version import __version__
from ._deps import state

router = APIRouter(tags=["system"])
log = logging.getLogger("automate.system")


@router.get("/health")
def health():
    return {"ok": True, "version": __version__}


@router.get("/status")
def status(s=Depends(state)):
    return {
        "version": __version__,
        "active_provider": s.providers.active_provider_id(),
        "active_model": s.providers.active_model(),
        "providers": len(s.db.list_providers()),
        "providers_configured": sum(1 for p in s.db.list_providers() if p["api_key_set"]),
        "integrations": len(s.db.list_connections()),
        "integrations_connected": sum(1 for c in s.db.list_connections() if c["status"] == "connected"),
        "tools": len(s.registry.all()),
        "extension_connected": bus.connected,
    }


# ---------------------------------------------------------------- storage dir

class StorageIn(BaseModel):
    path: str


@router.get("/system/storage")
def get_storage(s=Depends(state)):
    """Where new file/video uploads land. Reflects the user's setting
    (or the default if they haven't picked one yet)."""
    current = F.storage_dir(s.db)
    configured = s.db.get_setting(F.STORAGE_DIR_KEY)
    used = F.total_size(s.db)
    return {
        "current": str(current),
        "default": str(PATHS.files),
        "is_default": not configured,
        "used_bytes": used,
    }


@router.put("/system/storage")
def put_storage(body: StorageIn, s=Depends(state)):
    try:
        new_path = F.set_storage_dir(s.db, body.path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"current": str(new_path), "is_default": False}


# ---------------------------------------------------------------- update check

DEFAULT_REPO = "yuruotong1/autoMate"
DEFAULT_API = f"https://api.github.com/repos/{DEFAULT_REPO}/releases/latest"

# Cache one resolved release for 6 hours so repeated UI clicks don't
# hammer GitHub (or whichever mirror is configured).
_CACHE: dict = {"at": 0.0, "data": None, "url": ""}
_CACHE_TTL = 6 * 3600


@router.get("/system/update_check")
def update_check(mirror: str = Query(""), force: bool = Query(False)):
    """Resolve the latest release and tell the client whether a newer one
    is available. Designed to fail soft: any network / parse error
    returns a structured ``{current, error}`` instead of a 500.

    Mirrors: pass ``?mirror=ghproxy.com`` (or any prefix) to route the
    download URLs through a CN-friendly proxy. The default
    ``AUTOMATE_UPDATE_URL`` env var lets the operator override the
    metadata source too.
    """
    metadata_url = (os.environ.get("AUTOMATE_UPDATE_URL") or DEFAULT_API).strip()
    cache_key = f"{metadata_url}|{mirror}"
    now = time.time()
    if not force and _CACHE.get("url") == cache_key and (now - _CACHE["at"]) < _CACHE_TTL:
        return _CACHE["data"]

    try:
        req = urllib.request.Request(metadata_url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "automate-update-check",
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.URLError as e:
        return {"current": __version__, "error": f"update server unreachable: {e.reason}"}
    except (json.JSONDecodeError, KeyError) as e:
        return {"current": __version__, "error": f"malformed update payload: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"current": __version__, "error": str(e)}

    latest_tag = (payload.get("tag_name") or "").lstrip("v")
    release_url = payload.get("html_url", "")
    body = payload.get("body") or ""
    assets = payload.get("assets") or []

    # Index assets by filename suffix so the client knows which artifact
    # to fetch on which platform.
    by_platform = _index_assets(assets, mirror=mirror)

    data = {
        "current": __version__,
        "latest": latest_tag or None,
        "newer": _is_newer(latest_tag, __version__) if latest_tag else False,
        "release_notes_url": release_url,
        "release_notes_body": body[:4000],
        "download_urls": by_platform,
        "source": "mirror" if mirror else "github",
    }
    _CACHE.update({"at": now, "data": data, "url": cache_key})
    return data


# ------- helpers -------

_PLATFORM_PATTERNS = {
    "windows": ("windows-x64.zip",),
    "macos":   ("macos-arm64.zip", "darwin-arm64.zip"),
    "linux":   ("linux-x64.tar.gz", "linux-amd64.tar.gz"),
    "android": ("android.apk",),
    "wheel":   (".whl",),
    "sdist":   (".tar.gz",),    # generic; matched last so linux wins first
    "extension": ("extension.zip",),
}


def _index_assets(assets: list[dict], *, mirror: str) -> dict[str, str]:
    out: dict[str, str] = {}
    seen: set[str] = set()
    for plat, suffixes in _PLATFORM_PATTERNS.items():
        for asset in assets:
            name = asset.get("name") or ""
            if name in seen:
                continue
            for suf in suffixes:
                if name.endswith(suf):
                    url = asset.get("browser_download_url") or ""
                    out[plat] = _via_mirror(url, mirror)
                    seen.add(name)
                    break
    return out


def _via_mirror(url: str, mirror: str) -> str:
    if not mirror or not url.startswith("https://github.com/"):
        return url
    host = mirror.rstrip("/")
    if not host.startswith("http"):
        host = f"https://{host}"
    return f"{host}/{url}"


def _is_newer(latest: str, current: str) -> bool:
    """Compare two semver-ish strings. False if anything is fishy."""
    def parts(v: str) -> list[int]:
        return [int(x) for x in v.replace("-", ".").split(".") if x.isdigit()]
    try:
        return parts(latest) > parts(current)
    except Exception:  # noqa: BLE001
        return False
