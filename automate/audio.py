"""Audio transcription — multi-provider with custom vocabulary.

The user's pitch: phone-side meeting recorder with proper-noun accuracy.
Whisper alone misses Chinese names; Tencent ASR has hot-word support;
faster-whisper is heavy. So we ship a provider abstraction and pick at
runtime based on what's connected.

Providers in order of preference:
1. **tencent_asr** — best Chinese accuracy, accepts a hot-word list
   (custom vocabulary). Selected when ``tencent_asr`` connection has
   secret_id + secret_key configured.
2. **openai_whisper** — universal, fluent Chinese. Selected when an
   OpenAI provider has ``api_key`` set. Hot-words injected via the
   ``prompt`` argument.

All transcription is gated ``tier="pro"`` because each call costs us
inference money. The agent loop's tier check returns
``needs_pro_subscription`` to the LLM if the user isn't signed in to
autoMate Cloud — see ``automate/auth.py`` and ``docs/cloud.md``.

Custom vocabulary is mined locally from notes + chat history via
TF-IDF. We keep it on-device; the cloud server never sees the user's
private corpus, only the small set of proper nouns we send as a
hot-word list per call.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .store import Database, get_db

log = logging.getLogger("automate.audio")

# ----- vocabulary mining (local) -----------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{3,}|[一-龥]{2,4}")
_STOP = {
    # English filler
    "the", "and", "for", "you", "this", "that", "with", "are", "was", "but",
    "have", "has", "from", "they", "will", "your", "what", "when", "how",
    # Common Chinese tokens that aren't usually proper nouns
    "我们", "他们", "你们", "什么", "为什么", "怎么", "因为", "所以", "可以",
    "现在", "时候", "知道", "觉得", "可能", "需要", "已经",
}


def mine_vocabulary(db: Database, *, top_n: int = 50) -> list[str]:
    """TF-IDF-ish proper-noun extraction from local notes + chat.

    We lean on capitalisation (English) and bigram frequency (Chinese)
    rather than a real model. Cheap, local, deterministic. The result
    is the hot-word list we ship to ASR providers per call.
    """
    docs: list[str] = []
    try:
        rows = db.fetchall("SELECT title, body FROM notes ORDER BY updated_at DESC LIMIT 200")
        docs.extend(f"{r['title']} {r['body']}" for r in rows)
    except Exception:  # noqa: BLE001
        pass
    try:
        rows = db.fetchall(
            "SELECT result FROM runs WHERE status='done' ORDER BY started_at DESC LIMIT 200"
        )
        docs.extend(r["result"] or "" for r in rows)
    except Exception:  # noqa: BLE001
        pass

    if not docs:
        return []

    # Document frequencies (how many docs each term appears in).
    df: Counter[str] = Counter()
    tf_total: Counter[str] = Counter()
    for doc in docs:
        terms = {t for t in _TOKEN_RE.findall(doc) if t.lower() not in _STOP}
        for term in terms:
            df[term] += 1
        for term in _TOKEN_RE.findall(doc):
            if term.lower() in _STOP:
                continue
            tf_total[term] += 1

    n = len(docs)
    scored: list[tuple[float, str]] = []
    for term, count in tf_total.items():
        if count < 2:
            continue       # noise
        idf = max(0.5, _log(n / (1 + df[term])))
        # Weight by capitalised English (likely proper noun) and Chinese length 2-4 (term-y).
        bonus = 1.5 if term[0].isupper() and term[0].isalpha() else 1.0
        scored.append((count * idf * bonus, term))

    scored.sort(reverse=True)
    return [term for _, term in scored[:top_n]]


def _log(x: float) -> float:
    import math
    return math.log(max(x, 1e-9))


# ----- provider selection --------------------------------------------------

@dataclass
class Provider:
    id: str
    label: str


def pick_provider(db: Database, prefer: str | None = None) -> Provider | None:
    """Select an available transcription provider.

    Order: explicit ``prefer`` → Tencent ASR (if connected) → OpenAI
    (if a provider with api_key exists) → None.
    """
    if prefer:
        if prefer == "tencent_asr" and _tencent_connected(db):
            return Provider("tencent_asr", "Tencent ASR")
        if prefer == "openai_whisper" and _openai_key(db):
            return Provider("openai_whisper", "OpenAI Whisper")
    if _tencent_connected(db):
        return Provider("tencent_asr", "Tencent ASR")
    if _openai_key(db):
        return Provider("openai_whisper", "OpenAI Whisper")
    return None


def _tencent_connected(db: Database) -> bool:
    row = db.get_connection("tencent_asr", decrypt=True)
    return bool(row and row.get("status") == "connected" and row.get("secret_id"))


def _openai_key(db: Database) -> str | None:
    for prov in db.list_providers():
        if prov.get("id", "").startswith("openai") and prov.get("api_key_set"):
            full = db.get_provider(prov["id"], decrypt=True)
            if full and full.get("api_key"):
                return full["api_key"]
    return None


# ----- transcription -------------------------------------------------------

def transcribe(*, audio_path: Path, db: Database | None = None,
               provider: str = "", language: str = "",
               with_vocab: bool = True) -> dict:
    """Transcribe one audio file. Returns ``{provider, text, ms,
    vocabulary_used}`` or raises.
    """
    db = db or get_db()
    selected = pick_provider(db, prefer=provider or None)
    if not selected:
        raise RuntimeError(
            "no transcription provider configured — connect Tencent ASR "
            "(Settings → Integrations) or set an OpenAI api_key"
        )
    vocab = mine_vocabulary(db) if with_vocab else []
    started = time.time()
    if selected.id == "tencent_asr":
        text = _transcribe_tencent(audio_path, db, vocab=vocab, language=language)
    elif selected.id == "openai_whisper":
        text = _transcribe_openai(audio_path, db, vocab=vocab, language=language)
    else:
        raise RuntimeError(f"unknown provider: {selected.id}")
    return {
        "provider": selected.id,
        "text": text,
        "ms": int((time.time() - started) * 1000),
        "vocabulary_used": vocab[:20],   # echo back what we sent
    }


def _transcribe_openai(path: Path, db: Database, *, vocab: list[str], language: str) -> str:
    """Whisper via OpenAI's audio/transcriptions endpoint.

    Hot-words go into the ``prompt`` arg — Whisper conditions on it,
    which biases the decoder toward those terms. Not as exact as
    Tencent's hot-word weighting but it works.
    """
    api_key = _openai_key(db)
    if not api_key:
        raise RuntimeError("OpenAI api_key not configured")
    import urllib.request
    boundary = "----automateAudioBoundary"
    body = []
    def add_field(name, value):
        body.append(f"--{boundary}\r\n".encode())
        body.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.append(value.encode() + b"\r\n")
    add_field("model", "whisper-1")
    if language:
        add_field("language", language)
    if vocab:
        add_field("prompt", ", ".join(vocab[:50]))
    body.append(f"--{boundary}\r\n".encode())
    body.append(
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f'Content-Type: audio/mpeg\r\n\r\n'.encode()
    )
    body.append(path.read_bytes())
    body.append(f"\r\n--{boundary}--\r\n".encode())
    data = b"".join(body)
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        payload = json.loads(r.read().decode())
    return payload.get("text", "").strip()


def _transcribe_tencent(path: Path, db: Database, *, vocab: list[str], language: str) -> str:
    """Tencent ASR via their CreateRecTask (async) or short-form endpoint.

    For files under 60s we use SentenceRecognition (sync, simpler).
    Hot-words go in ``HotwordList``: a comma-separated 'word|weight'
    string. Default weight 5/10 — high enough to bias, not so high it
    overrides clear phonemes.
    """
    row = db.get_connection("tencent_asr", decrypt=True)
    if not row or not row.get("secret_id") or not row.get("secret_key"):
        raise RuntimeError("Tencent ASR connection not configured")
    # Defer the heavy SDK import.
    try:
        from tencentcloud.common import credential
        from tencentcloud.asr.v20190614 import asr_client, models
    except ImportError as e:
        raise RuntimeError(
            "tencentcloud-sdk-python not installed — pip install "
            "tencentcloud-sdk-python-asr"
        ) from e
    cred = credential.Credential(row["secret_id"], row["secret_key"])
    client = asr_client.AsrClient(cred, "")
    audio_b64 = _b64(path.read_bytes())
    req = models.SentenceRecognitionRequest()
    payload: dict = {
        "ProjectId": 0,
        "SubServiceType": 2,
        "EngSerViceType": "16k_zh" if (language or "zh") == "zh" else "16k_en",
        "SourceType": 1,
        "VoiceFormat": path.suffix.lstrip(".") or "wav",
        "UsrAudioKey": "automate",
        "Data": audio_b64,
        "DataLen": len(audio_b64),
    }
    if vocab:
        payload["HotwordList"] = ",".join(f"{w}|5" for w in vocab[:128])
    req.from_json_string(json.dumps(payload))
    resp = client.SentenceRecognition(req)
    return json.loads(resp.to_json_string()).get("Result", "").strip()


def _b64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode()
