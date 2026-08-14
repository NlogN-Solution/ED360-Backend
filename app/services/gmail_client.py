from __future__ import annotations

"""Thin wrapper around Google's OAuth token endpoint and the Gmail API.

Contains ONLY HTTP calls to Google — no CRM logic, no database access, no
organization/tenant awareness, mirroring whatsapp_client.py's separation
(Router -> Service -> Client -> Provider API).

Sync is polling-based (see gmail_service.sync_account, called from a
background loop in main.py) rather than webhook-based. Gmail's only push
mechanism is "watch" + Google Cloud Pub/Sub — a separate GCP resource this
codebase deliberately doesn't take on, matching the existing "no external
task queue, in-process sweeps" pattern already used for the WhatsApp retry
loop and the follow-up reminder loop.
"""

import base64
import logging
from typing import Any

import httpx

from ..core.config import get_settings

logger = logging.getLogger("ignition.email.gmail_client")

TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
# Deliberately gmail.readonly + gmail.send, NOT gmail.modify — this code
# never calls a labels/modify endpoint (no server-side mark-as-read/archive;
# "read" state lives entirely in EmailThread.last_read_at, not Gmail
# labels). That matters beyond least-privilege: gmail.modify is a Google
# *restricted* scope requiring a paid CASA security assessment to verify for
# production, while gmail.readonly is only "sensitive" (real verification,
# but no CASA). Don't add gmail.modify unless the code actually starts
# calling messages.modify — it changes what App Review demands.
OAUTH_SCOPES = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"


class GmailAPIError(RuntimeError):
    """A non-2xx response from Google. Carries Google's own error body (never
    a token/secret) so callers can surface a useful message without logging
    credentials."""

    def __init__(self, status_code: int, error_body: dict[str, Any] | str):
        self.status_code = status_code
        self.error_body = error_body
        message = error_body
        if isinstance(error_body, dict):
            message = error_body.get("error_description") or error_body.get("error", {}).get(
                "message", str(error_body)
            )
        super().__init__(f"Gmail API error ({status_code}): {message}")


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def _request(method: str, url: str, access_token: str, **kwargs: Any) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(method, url, headers=_headers(access_token), **kwargs)
    if response.status_code >= 400:
        try:
            body = response.json()
        except ValueError:
            body = response.text
        raise GmailAPIError(response.status_code, body)
    return response.json()


async def exchange_code_for_token(code: str, redirect_uri: str) -> dict[str, Any]:
    """POST /token with grant_type=authorization_code — the final step of
    Embedded-Signup-style connect. redirect_uri must exactly match what the
    frontend used to open the consent popup, or Google rejects the exchange."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if response.status_code >= 400:
        try:
            body = response.json()
        except ValueError:
            body = response.text
        raise GmailAPIError(response.status_code, body)
    return response.json()


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """POST /token with grant_type=refresh_token — called by gmail_service
    whenever the stored access token is expired or about to expire. Does not
    return a new refresh_token (Google keeps the original valid indefinitely
    unless the user revokes access)."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if response.status_code >= 400:
        try:
            body = response.json()
        except ValueError:
            body = response.text
        raise GmailAPIError(response.status_code, body)
    return response.json()


async def get_profile(access_token: str) -> dict[str, Any]:
    """GET /profile — the live validation call used right after connecting,
    and the source of the account's own email address (Gmail's `emailAddress`
    field), so we never have to ask the user to type it."""
    return await _request("GET", f"{GMAIL_API_BASE}/profile", access_token)


async def list_history(access_token: str, start_history_id: str) -> dict[str, Any]:
    """GET /history — incremental sync since the last known historyId. Can
    raise GmailAPIError(404, ...) if start_history_id is too old (Gmail only
    retains ~7 days of history); the caller falls back to list_recent_messages."""
    return await _request(
        "GET",
        f"{GMAIL_API_BASE}/history",
        access_token,
        params={"startHistoryId": start_history_id, "historyTypes": "messageAdded"},
    )


async def list_recent_messages(access_token: str, query: str, max_results: int = 50) -> dict[str, Any]:
    """GET /messages — full-list fallback used on first-ever sync, and
    whenever list_history's cursor has gone stale. `query` uses Gmail's
    search syntax (e.g. "newer_than:7d")."""
    return await _request(
        "GET", f"{GMAIL_API_BASE}/messages", access_token, params={"q": query, "maxResults": max_results}
    )


async def get_message(access_token: str, message_id: str) -> dict[str, Any]:
    """GET /messages/{id}?format=full — full MIME structure, parsed by
    gmail_service into body text/html + attachment metadata."""
    return await _request("GET", f"{GMAIL_API_BASE}/messages/{message_id}", access_token, params={"format": "full"})


async def get_attachment_bytes(access_token: str, message_id: str, attachment_id: str) -> bytes:
    """GET /messages/{id}/attachments/{attachmentId} — Gmail returns the
    bytes base64url-encoded inline in the JSON body (unlike Meta's WhatsApp
    API, no separate URL-fetch step)."""
    data = await _request(
        "GET", f"{GMAIL_API_BASE}/messages/{message_id}/attachments/{attachment_id}", access_token
    )
    raw = data.get("data", "")
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


async def send_message(access_token: str, raw_message_base64url: str, thread_id: str | None = None) -> dict[str, Any]:
    """POST /messages/send — raw_message_base64url is a full RFC 2822 MIME
    message, base64url-encoded (see gmail_service._build_mime_message).
    Passing thread_id keeps a reply in the same Gmail thread; omit it to
    start a new one."""
    payload: dict[str, Any] = {"raw": raw_message_base64url}
    if thread_id:
        payload["threadId"] = thread_id
    return await _request("POST", f"{GMAIL_API_BASE}/messages/send", access_token, json=payload)
