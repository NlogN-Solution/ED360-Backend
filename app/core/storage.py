"""File storage — Cloudinary in production, local disk for dev.

Render's filesystem is ephemeral (wiped on every deploy/restart), so
anything saved under `settings.upload_dir` there is lost the moment the
instance restarts. Every upload call site in this app used to write
straight to local disk; they now go through here instead, which uses
Cloudinary when it's configured (CLOUDINARY_CLOUD_NAME set) and falls back
to the exact old local-disk behavior when it isn't — so local dev keeps
working with zero setup, same as every other optional integration in
app/core/config.py.
"""
from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import cloudinary
import cloudinary.uploader
import httpx

from .config import get_settings

_configured = False


def _cloudinary_ready() -> bool:
    global _configured
    settings = get_settings()
    if not settings.CLOUDINARY_CLOUD_NAME:
        return False
    if not _configured:
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )
        _configured = True
    return True


def parse_cloudinary_url(url: str) -> tuple[str, str] | None:
    """https://res.cloudinary.com/<cloud>/<resource_type>/upload/v<ver>/<public_id>.<ext>
    -> (resource_type, public_id). Returns None if `url` isn't a Cloudinary URL."""
    marker = "res.cloudinary.com/"
    if marker not in url:
        return None
    try:
        after_cloud = url.split(marker, 1)[1].split("/", 1)[1]  # "<resource_type>/upload/v.../<public_id>.<ext>"
        resource_type, rest = after_cloud.split("/", 1)
        _delivery_type, rest = rest.split("/", 1)  # usually "upload"
        segments = rest.split("/")
        if segments and segments[0].startswith("v") and segments[0][1:].isdigit():
            segments = segments[1:]
        public_id = "/".join(segments).rsplit(".", 1)[0]
        return resource_type, public_id
    except (IndexError, ValueError):
        return None


def save_upload(content: bytes, filename: str, folder: str = "uploads") -> str:
    """Persist an uploaded file's bytes and return the URL to store on the
    record. `filename` is only used for its extension."""
    if _cloudinary_ready():
        extension = Path(filename).suffix.lstrip(".")
        result = cloudinary.uploader.upload(
            io.BytesIO(content),
            folder=folder,
            resource_type="auto",
            format=extension or None,
            use_filename=True,
            unique_filename=True,
        )
        return result["secure_url"]

    settings = get_settings()
    stored_file_name = f"{uuid4()}{Path(filename).suffix}"
    (settings.upload_dir / stored_file_name).write_bytes(content)
    return f"/uploads/{stored_file_name}"


def delete_upload(url: str | None) -> None:
    if not url:
        return
    if url.startswith("http"):
        parsed = parse_cloudinary_url(url)
        if parsed and _cloudinary_ready():
            resource_type, public_id = parsed
            cloudinary.uploader.destroy(public_id, resource_type=resource_type, invalidate=True)
        return

    settings = get_settings()
    (settings.upload_dir / Path(url).name).unlink(missing_ok=True)


async def read_upload(url: str) -> bytes:
    """The inverse of save_upload — used where a previously-uploaded file's
    bytes need to be read back (e.g. re-attaching to an outgoing email)."""
    if url.startswith("http"):
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    settings = get_settings()
    return (settings.upload_dir / Path(url).name).read_bytes()
