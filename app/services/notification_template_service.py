from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import NotificationTemplate
from ..models.enums import NotificationTemplateKey

# Built-in starting content for every template — used whenever an org hasn't
# saved a customized row for that key yet, so notifications always have
# sensible text out of the box.
DEFAULT_TEMPLATES: dict[NotificationTemplateKey, tuple[str, str]] = {
    NotificationTemplateKey.LEAD_WELCOME: (
        "New lead assigned",
        "{{lead_name}} was assigned to you.",
    ),
    NotificationTemplateKey.FOLLOW_UP_REMINDER: (
        "Follow-up due",
        "{{lead_name}} ({{lead_priority}}) has an overdue follow-up.",
    ),
    NotificationTemplateKey.APPLICATION_SUBMITTED: (
        "Application submitted",
        "Your application for {{program_name}} at {{university_name}} has been submitted.",
    ),
    NotificationTemplateKey.OFFER_RECEIVED: (
        "Offer received",
        "Good news — you've received an offer for {{program_name}} at {{university_name}}.",
    ),
    NotificationTemplateKey.DOCUMENT_REQUIRED: (
        "Document required",
        "Please submit {{document_name}} for your application to {{program_name}}.",
    ),
    NotificationTemplateKey.VISA_UPDATE: (
        "Visa update",
        "There's an update on your visa status for {{program_name}}: {{status}}.",
    ),
    NotificationTemplateKey.PAYMENT_REMINDER: (
        "Payment reminder",
        "This is a reminder that a payment of {{amount}} is pending.",
    ),
    NotificationTemplateKey.STAFF_NOTIFICATION: (
        "New activity",
        "{{message}}",
    ),
}

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _substitute(text: str, context: dict[str, Any]) -> str:
    return _PLACEHOLDER_RE.sub(lambda m: str(context.get(m.group(1), m.group(0))), text)


class NotificationTemplateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_row(self, organization_id: UUID, key: NotificationTemplateKey) -> NotificationTemplate | None:
        result = await self.session.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.organization_id == organization_id, NotificationTemplate.key == key
            )
        )
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> list[NotificationTemplate | dict[str, Any]]:
        """Always returns exactly 8 entries (DB row or a virtual default) so
        the settings UI has something editable for every key."""
        result = await self.session.execute(
            select(NotificationTemplate).where(NotificationTemplate.organization_id == organization_id)
        )
        rows = {row.key: row for row in result.scalars().all()}

        items: list[NotificationTemplate | dict[str, Any]] = []
        for key in NotificationTemplateKey:
            if key in rows:
                items.append(rows[key])
            else:
                subject, body = DEFAULT_TEMPLATES[key]
                items.append({"key": key, "subject": subject, "body": body, "is_active": True})
        return items

    async def upsert(self, organization_id: UUID, key: NotificationTemplateKey, data: dict[str, Any]) -> NotificationTemplate:
        row = await self._get_row(organization_id, key)
        if row is None:
            default_subject, default_body = DEFAULT_TEMPLATES[key]
            row = NotificationTemplate(
                organization_id=organization_id,
                key=key,
                subject=data.get("subject") or default_subject,
                body=data.get("body") or default_body,
                is_active=data.get("is_active", True),
            )
            self.session.add(row)
        else:
            for field, value in data.items():
                setattr(row, field, value)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def render(self, organization_id: UUID, key: NotificationTemplateKey, context: dict[str, Any]) -> tuple[str, str]:
        """Effective (subject, body) for this org+key, with {{placeholder}}
        tokens substituted from context. Falls back to the built-in default
        whenever there's no customized row, or the row is inactive."""
        row = await self._get_row(organization_id, key)
        if row is not None and row.is_active:
            subject, body = row.subject, row.body
        else:
            subject, body = DEFAULT_TEMPLATES[key]
        return _substitute(subject, context), _substitute(body, context)
