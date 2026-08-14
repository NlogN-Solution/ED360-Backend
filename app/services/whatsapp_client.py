from __future__ import annotations

"""Thin wrapper around the Meta WhatsApp Business Cloud API (the Graph API).

Contains ONLY HTTP calls to Meta — no CRM logic, no database access, no
organization/tenant awareness. Every function takes whatever credentials it
needs as explicit arguments rather than holding state, so the caller
(whatsapp_service.py) is the only place that knows which organization/account
those credentials belong to. This separation is deliberate — see the plan's
"Router -> Service -> Repository" / "Service -> WhatsAppClient -> Meta API"
layering.
"""

import logging
from typing import Any

import httpx

from ..core.config import get_settings

logger = logging.getLogger("ignition.whatsapp.client")


class WhatsAppAPIError(RuntimeError):
    """A non-2xx response from Meta. Carries Meta's own error body (never a
    token/secret) so callers can surface a useful message without logging
    credentials."""

    def __init__(self, status_code: int, error_body: dict[str, Any] | str):
        self.status_code = status_code
        self.error_body = error_body
        message = error_body
        if isinstance(error_body, dict):
            message = error_body.get("error", {}).get("message", str(error_body))
        super().__init__(f"WhatsApp API error ({status_code}): {message}")


def _base_url() -> str:
    settings = get_settings()
    return f"{settings.META_GRAPH_API_URL}/{settings.META_API_VERSION}"


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


async def _request(method: str, url: str, access_token: str, **kwargs: Any) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(method, url, headers=_headers(access_token), **kwargs)
    if response.status_code >= 400:
        try:
            body = response.json()
        except ValueError:
            body = response.text
        raise WhatsAppAPIError(response.status_code, body)
    return response.json()


async def verify_credentials(phone_number_id: str, access_token: str) -> dict[str, Any]:
    """GET /{phone_number_id} — the live validation call used before we
    persist a manually-entered connection. Raises WhatsAppAPIError if the
    phone_number_id or token is invalid, which is exactly the signal the
    Connect flow needs. Reused after Embedded Signup too, to confirm the
    token Meta just issued actually has access to the phone number the
    frontend claims it does — see IntegrationService.connect_whatsapp_embedded_signup."""
    url = f"{_base_url()}/{phone_number_id}"
    return await _request("GET", url, access_token, params={"fields": "verified_name,display_phone_number"})


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    """GET /oauth/access_token — the final step of Embedded Signup. Uses this
    platform's own Meta App id/secret (one App shared by every organization),
    never an org-specific credential; the `code` is what ties the resulting
    token to whichever business the user picked in the Meta popup."""
    settings = get_settings()
    url = f"{_base_url()}/oauth/access_token"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            url,
            params={
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "code": code,
            },
        )
    if response.status_code >= 400:
        try:
            body = response.json()
        except ValueError:
            body = response.text
        raise WhatsAppAPIError(response.status_code, body)
    return response.json()


async def get_client_business_id(access_token: str) -> str | None:
    """GET /me?fields=client_business_id — only a Business Integration System
    User (BISU) token carries this field. We use its presence as a proxy for
    "this token was issued by a System-user access token Embedded Signup
    configuration" (never-expires, right for our unattended send/receive
    use case) vs. "someone created a User access token configuration by
    mistake" (short-lived, will silently start failing in weeks — we never
    built a refresh flow because BISU tokens shouldn't need one). Best-effort:
    returns None on any error rather than raising, since this is a soft
    diagnostic check, not a precondition for connecting."""
    try:
        url = f"{_base_url()}/me"
        response = await _request("GET", url, access_token, params={"fields": "client_business_id"})
    except WhatsAppAPIError:
        return None
    return response.get("client_business_id")


async def subscribe_app_to_waba(waba_id: str, access_token: str) -> dict[str, Any]:
    """POST /{waba_id}/subscribed_apps — without this call, Meta never
    delivers webhook events (inbound messages, status updates) for this WABA
    to us, even though the token and phone number are otherwise valid. The
    manual-entry flow tells the org to do the equivalent via Meta Business
    Manager themselves; Embedded Signup does it here instead."""
    url = f"{_base_url()}/{waba_id}/subscribed_apps"
    return await _request("POST", url, access_token)


async def send_text_message(phone_number_id: str, access_token: str, to: str, body: str) -> dict[str, Any]:
    url = f"{_base_url()}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    return await _request("POST", url, access_token, json=payload)


async def send_template_message(
    phone_number_id: str,
    access_token: str,
    to: str,
    template_name: str,
    language_code: str,
    body_parameters: list[str] | None = None,
) -> dict[str, Any]:
    url = f"{_base_url()}/{phone_number_id}/messages"
    components = []
    if body_parameters:
        components.append(
            {"type": "body", "parameters": [{"type": "text", "text": value} for value in body_parameters]}
        )
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            **({"components": components} if components else {}),
        },
    }
    return await _request("POST", url, access_token, json=payload)


async def send_media_message(
    phone_number_id: str,
    access_token: str,
    to: str,
    media_type: str,
    link: str,
    caption: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    """media_type is "image" or "document". `link` must be a publicly
    fetchable URL — Meta downloads it server-side; it does not accept
    arbitrary local file paths."""
    url = f"{_base_url()}/{phone_number_id}/messages"
    media_object: dict[str, Any] = {"link": link}
    if caption:
        media_object["caption"] = caption
    if filename and media_type == "document":
        media_object["filename"] = filename
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": media_type,
        media_type: media_object,
    }
    return await _request("POST", url, access_token, json=payload)


async def mark_as_read(phone_number_id: str, access_token: str, message_id: str) -> dict[str, Any]:
    url = f"{_base_url()}/{phone_number_id}/messages"
    payload = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
    return await _request("POST", url, access_token, json=payload)


async def fetch_message_templates(waba_id: str, access_token: str) -> list[dict[str, Any]]:
    url = f"{_base_url()}/{waba_id}/message_templates"
    templates: list[dict[str, Any]] = []
    params: dict[str, Any] = {"limit": 100}
    async with httpx.AsyncClient(timeout=30.0) as client:
        next_url: str | None = url
        while next_url:
            response = await client.get(next_url, headers=_headers(access_token), params=params if next_url == url else None)
            if response.status_code >= 400:
                try:
                    body = response.json()
                except ValueError:
                    body = response.text
                raise WhatsAppAPIError(response.status_code, body)
            data = response.json()
            templates.extend(data.get("data", []))
            next_url = data.get("paging", {}).get("next")
    return templates


async def get_media_url(media_id: str, access_token: str) -> dict[str, Any]:
    """Step 1 of downloading inbound media: resolve a Meta media id to a
    short-lived download URL + mime type."""
    url = f"{_base_url()}/{media_id}"
    return await _request("GET", url, access_token)


async def download_media(media_url: str, access_token: str) -> bytes:
    """Step 2: fetch the actual bytes from the URL get_media_url() returned.
    Requires the same bearer token — Meta's media URLs are not public."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(media_url, headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code >= 400:
        raise WhatsAppAPIError(response.status_code, response.text)
    return response.content
