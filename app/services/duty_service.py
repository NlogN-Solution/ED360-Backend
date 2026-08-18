from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import (
    Duty,
    DutyAcknowledgement,
    DutyDepartment,
    DutyRole,
    DutyUser,
    DutyVersion,
    EmployeeProfile,
    User,
)
from ..models.enums import ActivityType, DutyStatus, NotificationType, UserStatus
from ..schemas.duty import AcknowledgementStatus, DutyAcknowledgementSummary, UserRef
from .activity_log_service import ActivityLogService
from .notification_service import NotificationService


class DutyValidationError(ValueError):
    pass


class DutyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.activity_log_service = ActivityLogService(session)
        self.notification_service = NotificationService(session)

    def _base_query(self):
        return select(Duty).options(
            selectinload(Duty.current_version),
            selectinload(Duty.role_assignments).selectinload(DutyRole.job_role),
            selectinload(Duty.department_assignments).selectinload(DutyDepartment.department),
            selectinload(Duty.user_assignments).selectinload(DutyUser.user),
        )

    async def get_duty(self, duty_id: UUID, organization_id: UUID | None = None) -> Duty | None:
        query = self._base_query().where(Duty.id == duty_id)
        if organization_id is not None:
            query = query.where(Duty.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.unique().scalar_one_or_none()

    # --- visibility ------------------------------------------------------------

    async def _employee_profile_targets(self, user_id: UUID) -> tuple[UUID | None, UUID | None]:
        result = await self.session.execute(
            select(EmployeeProfile.job_role_id, EmployeeProfile.department_id).where(EmployeeProfile.user_id == user_id)
        )
        row = result.first()
        return (row.job_role_id, row.department_id) if row is not None else (None, None)

    async def is_applicable_to_user(self, duty: Duty, user: User) -> bool:
        if any(ua.user_id == user.id for ua in duty.user_assignments):
            return True
        job_role_id, department_id = await self._employee_profile_targets(user.id)
        if job_role_id and any(ra.job_role_id == job_role_id for ra in duty.role_assignments):
            return True
        if department_id and any(da.department_id == department_id for da in duty.department_assignments):
            return True
        return False

    async def has_acknowledged(self, duty_version_id: UUID, user_id: UUID) -> bool:
        result = await self.session.execute(
            select(DutyAcknowledgement.id).where(
                DutyAcknowledgement.duty_version_id == duty_version_id, DutyAcknowledgement.user_id == user_id
            )
        )
        return result.scalar_one_or_none() is not None

    async def _applicable_user_ids(self, duty: Duty) -> list[UUID]:
        job_role_ids = [ra.job_role_id for ra in duty.role_assignments]
        department_ids = [da.department_id for da in duty.department_assignments]
        direct_user_ids = [ua.user_id for ua in duty.user_assignments]

        conditions = []
        if direct_user_ids:
            conditions.append(User.id.in_(direct_user_ids))
        if job_role_ids or department_ids:
            profile_conditions = []
            if job_role_ids:
                profile_conditions.append(EmployeeProfile.job_role_id.in_(job_role_ids))
            if department_ids:
                profile_conditions.append(EmployeeProfile.department_id.in_(department_ids))
            conditions.append(User.id.in_(select(EmployeeProfile.user_id).where(or_(*profile_conditions))))
        if not conditions:
            return []

        result = await self.session.execute(
            select(User.id).where(User.organization_id == duty.organization_id, User.status == UserStatus.ACTIVE, or_(*conditions))
        )
        return [row[0] for row in result.all()]

    async def list_my_duties(self, organization_id: UUID, user: User, pending_only: bool = False) -> list[Duty]:
        job_role_id, department_id = await self._employee_profile_targets(user.id)

        conditions = [Duty.user_assignments.any(DutyUser.user_id == user.id)]
        if job_role_id:
            conditions.append(Duty.role_assignments.any(DutyRole.job_role_id == job_role_id))
        if department_id:
            conditions.append(Duty.department_assignments.any(DutyDepartment.department_id == department_id))

        query = self._base_query().where(
            Duty.organization_id == organization_id, Duty.status == DutyStatus.PUBLISHED, or_(*conditions)
        )
        result = await self.session.execute(query)
        duties = list(result.unique().scalars().all())

        version_ids = [d.current_version_id for d in duties if d.current_version_id is not None]
        acknowledged_version_ids: set[UUID] = set()
        if version_ids:
            ack_result = await self.session.execute(
                select(DutyAcknowledgement.duty_version_id).where(
                    DutyAcknowledgement.user_id == user.id, DutyAcknowledgement.duty_version_id.in_(version_ids)
                )
            )
            acknowledged_version_ids = {row[0] for row in ack_result.all()}

        for duty in duties:
            duty.is_acknowledged_by_me = duty.current_version_id in acknowledged_version_ids

        if pending_only:
            duties = [d for d in duties if d.requires_acknowledgement and not d.is_acknowledged_by_me]
        return duties

    # --- admin listing -----------------------------------------------------------

    async def list_duties(
        self,
        organization_id: UUID,
        page: int,
        limit: int,
        type_: str | None = None,
        category: str | None = None,
        status: str | None = None,
        department_id: UUID | None = None,
        job_role_id: UUID | None = None,
        user_id: UUID | None = None,
        search: str | None = None,
    ) -> tuple[list[Duty], int]:
        def apply_filters(q):
            if type_:
                q = q.where(Duty.type == type_)
            if category:
                q = q.where(Duty.category == category)
            if status:
                q = q.where(Duty.status == status)
            if department_id:
                q = q.where(Duty.department_assignments.any(DutyDepartment.department_id == department_id))
            if job_role_id:
                q = q.where(Duty.role_assignments.any(DutyRole.job_role_id == job_role_id))
            if user_id:
                q = q.where(Duty.user_assignments.any(DutyUser.user_id == user_id))
            if search:
                pattern = f"%{search}%"
                q = q.where(
                    Duty.current_version_id.in_(
                        select(DutyVersion.id).where(
                            or_(DutyVersion.title.ilike(pattern), DutyVersion.content.ilike(pattern))
                        )
                    )
                )
            return q

        base = apply_filters(select(Duty.id).where(Duty.organization_id == organization_id))
        total = await self.session.scalar(select(func.count()).select_from(base.subquery())) or 0

        query = apply_filters(self._base_query().where(Duty.organization_id == organization_id))
        query = query.order_by(Duty.created_at.desc()).limit(limit).offset((page - 1) * limit)
        result = await self.session.execute(query)
        duties = list(result.unique().scalars().all())

        for duty in duties:
            if duty.requires_acknowledgement and duty.current_version_id is not None:
                applicable_ids = await self._applicable_user_ids(duty)
                duty.applicable_count = len(applicable_ids)
                duty.acknowledged_count = (
                    await self.session.scalar(
                        select(func.count(func.distinct(DutyAcknowledgement.user_id))).where(
                            DutyAcknowledgement.duty_version_id == duty.current_version_id,
                            DutyAcknowledgement.user_id.in_(applicable_ids),
                        )
                    )
                    if applicable_ids
                    else 0
                )

        return duties, total

    # --- create / update -----------------------------------------------------------

    async def create_duty(self, organization_id: UUID, data: dict[str, Any], created_by: UUID) -> Duty:
        data = dict(data)
        job_role_ids = data.pop("job_role_ids", [])
        department_ids = data.pop("department_ids", [])
        user_ids = data.pop("user_ids", [])
        publish = data.pop("publish", False)
        title = data.pop("title")
        content = data.pop("content")

        duty = Duty(organization_id=organization_id, created_by=created_by, updated_by=created_by, **data)
        self.session.add(duty)
        await self.session.flush()

        version = DutyVersion(organization_id=organization_id, duty_id=duty.id, version=1, title=title, content=content, created_by=created_by)
        self.session.add(version)
        await self.session.flush()

        # Assign the relationship, not just the raw FK column — this session
        # runs with expire_on_commit=False, so a bare `.current_version_id =`
        # would leave the already-loaded `.current_version` relationship
        # stale in memory even after commit.
        duty.current_version = version
        if publish:
            version.published_at = datetime.now(timezone.utc)
            duty.status = DutyStatus.PUBLISHED

        for job_role_id in dict.fromkeys(job_role_ids):
            self.session.add(DutyRole(organization_id=organization_id, duty_id=duty.id, job_role_id=job_role_id))
        for department_id in dict.fromkeys(department_ids):
            self.session.add(DutyDepartment(organization_id=organization_id, duty_id=duty.id, department_id=department_id))
        for user_id in dict.fromkeys(user_ids):
            self.session.add(DutyUser(organization_id=organization_id, duty_id=duty.id, user_id=user_id))

        await self.session.commit()
        await self.activity_log_service.log(
            user_id=created_by,
            activity_type=ActivityType.CREATE,
            entity_type="duty",
            entity_id=duty.id,
            organization_id=organization_id,
            description=f"Created duty '{title}'" + (" and published it" if publish else " as a draft"),
        )
        result = await self.get_duty(duty.id, organization_id)
        assert result is not None
        if publish:
            await self._notify_published(result)
        return result

    async def _replace_assignments(self, duty: Duty, model: type, field_name: str, new_ids: list[UUID]) -> None:
        existing = await self.session.execute(select(model).where(model.duty_id == duty.id))
        existing_rows = list(existing.scalars().all())
        existing_ids = {getattr(row, field_name) for row in existing_rows}
        incoming = set(dict.fromkeys(new_ids))
        for row in existing_rows:
            if getattr(row, field_name) not in incoming:
                await self.session.delete(row)
        for id_ in incoming:
            if id_ not in existing_ids:
                self.session.add(model(organization_id=duty.organization_id, duty_id=duty.id, **{field_name: id_}))

    async def update_duty(self, duty: Duty, data: dict[str, Any], updated_by: UUID) -> Duty:
        data = dict(data)
        job_role_ids = data.pop("job_role_ids", None)
        department_ids = data.pop("department_ids", None)
        user_ids = data.pop("user_ids", None)
        title = data.pop("title", None)
        content = data.pop("content", None)

        for key, value in data.items():
            if value is not None:
                setattr(duty, key, value)
        duty.updated_by = updated_by

        if job_role_ids is not None:
            await self._replace_assignments(duty, DutyRole, "job_role_id", job_role_ids)
        if department_ids is not None:
            await self._replace_assignments(duty, DutyDepartment, "department_id", department_ids)
        if user_ids is not None:
            await self._replace_assignments(duty, DutyUser, "user_id", user_ids)

        version_bumped = False
        if title is not None or content is not None:
            current = duty.current_version
            if current is not None and current.published_at is None:
                # Nobody has seen this version yet — safe to edit in place.
                if title is not None:
                    current.title = title
                if content is not None:
                    current.content = content
            else:
                await self._create_version(duty, title, content, updated_by)
                version_bumped = True

        await self.session.commit()
        await self.activity_log_service.log(
            user_id=updated_by,
            activity_type=ActivityType.UPDATE,
            entity_type="duty",
            entity_id=duty.id,
            organization_id=duty.organization_id,
            description="Created a new draft version" if version_bumped else "Updated duty",
        )
        result = await self.get_duty(duty.id, duty.organization_id)
        assert result is not None
        return result

    async def _create_version(self, duty: Duty, title: str | None, content: str | None, created_by: UUID) -> DutyVersion:
        current = duty.current_version
        next_number = (current.version if current is not None else 0) + 1
        version = DutyVersion(
            organization_id=duty.organization_id,
            duty_id=duty.id,
            version=next_number,
            title=title if title is not None else (current.title if current is not None else ""),
            content=content if content is not None else (current.content if current is not None else ""),
            created_by=created_by,
        )
        self.session.add(version)
        await self.session.flush()
        return version

    async def create_version(self, duty: Duty, title: str | None, content: str | None, created_by: UUID) -> DutyVersion:
        version = await self._create_version(duty, title, content, created_by)
        await self.session.commit()
        await self.activity_log_service.log(
            user_id=created_by,
            activity_type=ActivityType.CREATE,
            entity_type="duty",
            entity_id=duty.id,
            organization_id=duty.organization_id,
            description=f"Created version {version.version}",
        )
        return version

    async def list_versions(self, duty_id: UUID) -> list[DutyVersion]:
        result = await self.session.execute(
            select(DutyVersion).where(DutyVersion.duty_id == duty_id).order_by(DutyVersion.version.desc())
        )
        return list(result.scalars().all())

    async def publish_version(self, duty: Duty, version_number: int, published_by: UUID) -> Duty:
        result = await self.session.execute(
            select(DutyVersion).where(DutyVersion.duty_id == duty.id, DutyVersion.version == version_number)
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise DutyValidationError(f"Version {version_number} not found")
        version.published_at = datetime.now(timezone.utc)
        duty.current_version = version  # relationship, not raw FK — see create_duty's comment
        duty.status = DutyStatus.PUBLISHED
        duty.updated_by = published_by
        await self.session.commit()
        await self.activity_log_service.log(
            user_id=published_by,
            activity_type=ActivityType.STATUS_CHANGE,
            entity_type="duty",
            entity_id=duty.id,
            organization_id=duty.organization_id,
            description=f"Published version {version_number}",
        )
        result_duty = await self.get_duty(duty.id, duty.organization_id)
        assert result_duty is not None
        await self._notify_published(result_duty)
        return result_duty

    async def publish_latest(self, duty: Duty, published_by: UUID) -> Duty:
        versions = await self.list_versions(duty.id)
        if not versions:
            raise DutyValidationError("This duty has no version to publish")
        return await self.publish_version(duty, versions[0].version, published_by)

    async def archive_duty(self, duty: Duty, archived_by: UUID) -> Duty:
        duty.status = DutyStatus.ARCHIVED
        duty.updated_by = archived_by
        await self.session.commit()
        await self.activity_log_service.log(
            user_id=archived_by,
            activity_type=ActivityType.STATUS_CHANGE,
            entity_type="duty",
            entity_id=duty.id,
            organization_id=duty.organization_id,
            description="Archived",
        )
        result = await self.get_duty(duty.id, duty.organization_id)
        assert result is not None
        return result

    async def delete_duty(self, duty: Duty, deleted_by: UUID) -> None:
        await self.activity_log_service.log(
            user_id=deleted_by,
            activity_type=ActivityType.DELETE,
            entity_type="duty",
            entity_id=duty.id,
            organization_id=duty.organization_id,
            description="Deleted",
        )
        await self.session.delete(duty)
        await self.session.commit()

    # --- acknowledgement -----------------------------------------------------------

    async def acknowledge(
        self, duty: Duty, user: User, ip_address: str | None, user_agent: str | None
    ) -> DutyAcknowledgement:
        if not duty.requires_acknowledgement:
            raise DutyValidationError("This duty does not require acknowledgement")
        if duty.status != DutyStatus.PUBLISHED or duty.current_version_id is None:
            raise DutyValidationError("This duty is not currently published")
        if not await self.is_applicable_to_user(duty, user):
            raise DutyValidationError("This duty does not apply to you")

        existing = await self.session.execute(
            select(DutyAcknowledgement).where(
                DutyAcknowledgement.duty_version_id == duty.current_version_id, DutyAcknowledgement.user_id == user.id
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise DutyValidationError("You have already acknowledged this version")

        ack = DutyAcknowledgement(
            organization_id=duty.organization_id,
            duty_id=duty.id,
            duty_version_id=duty.current_version_id,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(ack)
        await self.session.commit()
        await self.session.refresh(ack)
        await self.activity_log_service.log(
            user_id=user.id,
            activity_type=ActivityType.ACKNOWLEDGE,
            entity_type="duty",
            entity_id=duty.id,
            organization_id=duty.organization_id,
            description=f"Acknowledged version {duty.version}",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return ack

    async def get_acknowledgement_summary(self, duty: Duty) -> DutyAcknowledgementSummary:
        applicable_ids = await self._applicable_user_ids(duty)
        if not applicable_ids or duty.current_version_id is None:
            return DutyAcknowledgementSummary(duty_id=duty.id, version=duty.version or 0, total_applicable=0, total_acknowledged=0, statuses=[])

        users_result = await self.session.execute(select(User).where(User.id.in_(applicable_ids)).order_by(User.first_name))
        users = list(users_result.scalars().all())

        ack_result = await self.session.execute(
            select(DutyAcknowledgement).where(
                DutyAcknowledgement.duty_version_id == duty.current_version_id, DutyAcknowledgement.user_id.in_(applicable_ids)
            )
        )
        acks_by_user = {a.user_id: a for a in ack_result.scalars().all()}

        statuses = [
            AcknowledgementStatus(
                user=UserRef.model_validate(u),
                acknowledged=u.id in acks_by_user,
                acknowledged_at=acks_by_user[u.id].acknowledged_at if u.id in acks_by_user else None,
            )
            for u in users
        ]
        return DutyAcknowledgementSummary(
            duty_id=duty.id, version=duty.version or 0, total_applicable=len(users), total_acknowledged=len(acks_by_user), statuses=statuses
        )

    # --- notifications -----------------------------------------------------------

    async def _notify_published(self, duty: Duty) -> None:
        applicable_ids = await self._applicable_user_ids(duty)
        title = duty.title or "A duty"
        message = f"{title} (version {duty.version}) has been published."
        if duty.requires_acknowledgement:
            message += " Please review and acknowledge."
        for user_id in applicable_ids:
            await self.notification_service.create_notification(
                {
                    "user_id": user_id,
                    "type": NotificationType.DUTY,
                    "title": "New policy published" if duty.requires_acknowledgement else "New duty published",
                    "message": message,
                    "related_id": duty.id,
                    "organization_id": duty.organization_id,
                }
            )
