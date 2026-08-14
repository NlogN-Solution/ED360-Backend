from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Comment, Notification, User
from ..models.enums import CommentEntityType, NotificationType

# Which module a comment's notification should deep-link back into — mirrors
# the existing per-module NotificationType values (see notificationPath() on
# the frontend), so a comment notification opens the same way any other
# notification for that module already does.
ENTITY_NOTIFICATION_TYPE: dict[CommentEntityType, NotificationType] = {
    CommentEntityType.LEAD: NotificationType.LEAD,
    CommentEntityType.APPLICATION: NotificationType.APPLICATION,
    CommentEntityType.APPLICANT: NotificationType.APPLICANT,
}

COMMENT_PREVIEW_LENGTH = 140


class CommentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_comment(self, comment_id: UUID, organization_id: UUID | None = None) -> Comment | None:
        query = select(Comment).where(Comment.id == comment_id)
        if organization_id is not None:
            query = query.where(Comment.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_comments(
        self, entity_type: CommentEntityType, entity_id: UUID, organization_id: UUID | None
    ) -> list[Comment]:
        query = (
            select(Comment)
            .where(Comment.entity_type == entity_type, Comment.entity_id == entity_id)
            .order_by(Comment.created_at.asc())
        )
        if organization_id is not None:
            query = query.where(Comment.organization_id == organization_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_comments(
        self, entity_type: CommentEntityType, entity_ids: list[UUID], organization_id: UUID | None
    ) -> dict[str, int]:
        if not entity_ids:
            return {}
        query = (
            select(Comment.entity_id, func.count())
            .where(Comment.entity_type == entity_type, Comment.entity_id.in_(entity_ids))
            .group_by(Comment.entity_id)
        )
        if organization_id is not None:
            query = query.where(Comment.organization_id == organization_id)
        result = await self.session.execute(query)
        return {str(entity_id): count for entity_id, count in result.all()}

    async def create_comment(
        self,
        entity_type: CommentEntityType,
        entity_id: UUID,
        body: str,
        author: User,
        owner_id: UUID | None,
    ) -> Comment:
        comment = Comment(
            entity_type=entity_type,
            entity_id=entity_id,
            author_id=author.id,
            body=body,
            organization_id=author.organization_id,
        )
        self.session.add(comment)
        await self.session.commit()
        await self.session.refresh(comment)

        await self._notify_participants(entity_type, entity_id, author, owner_id, body)
        return comment

    async def delete_comment(self, comment: Comment) -> None:
        await self.session.delete(comment)
        await self.session.commit()

    async def _notify_participants(
        self,
        entity_type: CommentEntityType,
        entity_id: UUID,
        author: User,
        owner_id: UUID | None,
        body: str,
    ) -> None:
        # Notify whoever "owns" this record (assigned counsellor, etc.) plus
        # anyone else who has already commented on it — a comment thread, not
        # just a one-way ping to the owner. Author never notifies themselves.
        participants_query = select(Comment.author_id).where(
            Comment.entity_type == entity_type, Comment.entity_id == entity_id
        )
        result = await self.session.execute(participants_query)
        recipient_ids = {row[0] for row in result.all()}
        if owner_id is not None:
            recipient_ids.add(owner_id)
        recipient_ids.discard(author.id)
        if not recipient_ids:
            return

        author_name = f"{author.first_name} {author.last_name or ''}".strip()
        preview = body if len(body) <= COMMENT_PREVIEW_LENGTH else body[: COMMENT_PREVIEW_LENGTH - 1] + "…"
        notification_type = ENTITY_NOTIFICATION_TYPE[entity_type]
        for recipient_id in recipient_ids:
            self.session.add(
                Notification(
                    user_id=recipient_id,
                    organization_id=author.organization_id,
                    type=notification_type,
                    title=f"New comment from {author_name}",
                    message=preview,
                    related_id=entity_id,
                )
            )
        await self.session.commit()


async def get_comment_service(session: AsyncSession) -> CommentService:
    return CommentService(session)
