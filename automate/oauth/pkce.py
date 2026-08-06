"""PKCE (Proof Key for Code Exchange, RFC 7636) helpers.

For providers that support PKCE we don't need a `client_secret` at all —
the local hub generates a one-shot ``code_verifier``, sends a SHA256
``code_challenge`` to the provider with the authorization request, and
proves possession of the verifier on the token-exchange call. This lets
us ship a single ``client_id`` baked into autoMate without leaking any
secret.

Used by Linear, Atlassian (Jira/Confluence), Microsoft Graph (Teams),
Google, Twitter/X, Discord — every modern OAuth provider that follows
the OAuth 2.1 draft.
"""
from __future__ import annotations

import base64
import hashlib
import secrets


def make_verifier(length: int = 64) -> str:
    """43..128 chars of [A-Za-z0-9-._~] per RFC 7636 §4.1. 64 is plenty."""
    return secrets.token_urlsafe(length)[:length]


def make_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
