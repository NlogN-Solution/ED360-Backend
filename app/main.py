from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import router
from app.core.config import get_settings
from app.db.session import session_factory
from app.services.gmail_service import GmailService
from app.services.lead_service import LeadService
from app.services.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)

FOLLOW_UP_REMINDER_INTERVAL_SECONDS = 900  # 15 minutes
WHATSAPP_RETRY_INTERVAL_SECONDS = 120  # 2 minutes — no task queue exists in this codebase (see plan); this sweep is the only mechanism that ever re-attempts a message stuck PENDING/FAILED.
EMAIL_RETRY_INTERVAL_SECONDS = 120  # same rationale as WHATSAPP_RETRY_INTERVAL_SECONDS.
EMAIL_SYNC_INTERVAL_SECONDS = 120  # Gmail has no push webhook in this codebase (see gmail_client.py) — this poll is the only way inbound mail ever arrives.


async def _follow_up_reminder_loop() -> None:
    while True:
        try:
            async with session_factory() as session:
                sent = await LeadService(session).send_due_follow_up_reminders()
                if sent:
                    logger.info("Sent %d follow-up reminder notification(s)", sent)
        except Exception:
            logger.exception("Follow-up reminder sweep failed")
        await asyncio.sleep(FOLLOW_UP_REMINDER_INTERVAL_SECONDS)


async def _whatsapp_retry_loop() -> None:
    while True:
        try:
            async with session_factory() as session:
                retried = await WhatsAppService(session).retry_pending_outbound()
                if retried:
                    logger.info("Retried %d pending/failed WhatsApp message(s)", retried)
        except Exception:
            logger.exception("WhatsApp outbound retry sweep failed")
        await asyncio.sleep(WHATSAPP_RETRY_INTERVAL_SECONDS)


async def _email_sync_loop() -> None:
    while True:
        try:
            async with session_factory() as session:
                service = GmailService(session)
                for account in await service.list_connected_accounts():
                    try:
                        synced = await service.sync_account(account)
                        if synced:
                            logger.info("Synced %d new email message(s) for account %s", synced, account.id)
                    except Exception:
                        # One organization's Gmail hiccup (expired refresh
                        # token, transient API error) must not stop every
                        # other organization's sync this tick.
                        logger.exception("Email sync failed for account %s", account.id)
        except Exception:
            logger.exception("Email sync sweep failed")
        await asyncio.sleep(EMAIL_SYNC_INTERVAL_SECONDS)


async def _email_retry_loop() -> None:
    while True:
        try:
            async with session_factory() as session:
                retried = await GmailService(session).retry_pending_outbound()
                if retried:
                    logger.info("Retried %d pending/failed email message(s)", retried)
        except Exception:
            logger.exception("Email outbound retry sweep failed")
        await asyncio.sleep(EMAIL_RETRY_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        asyncio.create_task(_follow_up_reminder_loop()),
        asyncio.create_task(_whatsapp_retry_loop()),
        asyncio.create_task(_email_sync_loop()),
        asyncio.create_task(_email_retry_loop()),
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass


settings = get_settings()
app = FastAPI(
    title="Ignition CRM API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
