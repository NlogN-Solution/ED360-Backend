from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import INET, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.types import enum_type
from ..db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPKMixin
from .enums import EmploymentType, InstitutionType, UserRole, UserStatus


class User(Base, UUIDPKMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True)

    # Tenant identity. NULL only for platform administrators (is_platform_admin=True),
    # who belong to no single organization and bypass tenant scoping entirely.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
    )
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    @property
    def has_portal_access(self) -> bool:
        """No password set means the account can never authenticate — that's
        the "portal not yet enabled" state for a lead-converted student who
        wasn't given login credentials at conversion time."""
        return self.password_hash is not None

    role: Mapped[UserRole] = mapped_column(
        enum_type(UserRole, "user_role", create_type=False),
        nullable=False,
        server_default=UserRole.STUDENT.value,
    )

    status: Mapped[UserStatus] = mapped_column(
        enum_type(UserStatus, "user_status", create_type=False),
        nullable=False,
        server_default=UserStatus.ACTIVE.value,
    )

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(150))

    avatar_url: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(20))

    gender: Mapped[str | None] = mapped_column(String(20))
    date_of_birth: Mapped[date | None] = mapped_column(Date)

    email_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    phone_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    failed_login_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_login_ip: Mapped[str | None] = mapped_column(INET)

    student_profile: Mapped["StudentProfile | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    employee_profile: Mapped["EmployeeProfile | None"] = relationship(
        foreign_keys="[EmployeeProfile.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    leads_assigned: Mapped[list["Lead"]] = relationship(
        foreign_keys="[Lead.assigned_to]",
        back_populates="assignee",
        cascade="all, delete-orphan",
    )
    lead_converted_from: Mapped[list["Lead"]] = relationship(
        foreign_keys="[Lead.converted_user_id]",
        back_populates="converted_user",
        cascade="all, delete-orphan",
    )

    lead_activities_performed: Mapped[list["LeadActivity"]] = relationship(
        back_populates="performer",
        cascade="all, delete-orphan",
    )

    documents_owned: Mapped[list["Document"]] = relationship(
        foreign_keys="[Document.student_id]",
        back_populates="student",
        cascade="all, delete-orphan",
    )
    documents_uploaded: Mapped[list["Document"]] = relationship(
        foreign_keys="[Document.uploaded_by]",
        back_populates="uploader",
        cascade="all, delete-orphan",
    )
    documents_verified: Mapped[list["Document"]] = relationship(
        foreign_keys="[Document.verified_by]",
        back_populates="verifier",
        cascade="all, delete-orphan",
    )

    applications_as_student: Mapped[list["Application"]] = relationship(
        foreign_keys="[Application.student_id]",
        back_populates="student",
        cascade="all, delete-orphan",
    )
    applications_as_counsellor: Mapped[list["Application"]] = relationship(
        foreign_keys="[Application.counsellor_id]",
        back_populates="counsellor",
        cascade="all, delete-orphan",
    )

    appointments_as_student: Mapped[list["Appointment"]] = relationship(
        foreign_keys="[Appointment.student_id]",
        back_populates="student",
        cascade="all, delete-orphan",
    )
    appointments_as_counsellor: Mapped[list["Appointment"]] = relationship(
        foreign_keys="[Appointment.counsellor_id]",
        back_populates="counsellor",
        cascade="all, delete-orphan",
    )
    appointments_created: Mapped[list["Appointment"]] = relationship(
        foreign_keys="[Appointment.created_by]",
        back_populates="creator",
        cascade="all, delete-orphan",
    )

    tasks_assigned_to_me: Mapped[list["Task"]] = relationship(
        foreign_keys="[Task.assigned_to]",
        back_populates="assigned_to_user",
        cascade="all, delete-orphan",
    )
    tasks_assigned_by_me: Mapped[list["Task"]] = relationship(
        foreign_keys="[Task.assigned_by]",
        back_populates="assigned_by_user",
        cascade="all, delete-orphan",
    )
    tasks_for_student: Mapped[list["Task"]] = relationship(
        foreign_keys="[Task.student_id]",
        back_populates="student_user",
        cascade="all, delete-orphan",
    )

    payments_owned: Mapped[list["Payment"]] = relationship(
        foreign_keys="[Payment.student_id]",
        back_populates="student",
        cascade="all, delete-orphan",
    )
    payments_created: Mapped[list["Payment"]] = relationship(
        foreign_keys="[Payment.created_by]",
        back_populates="creator",
        cascade="all, delete-orphan",
    )

    subscription: Mapped["Subscription | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    user_sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    activity_logs: Mapped[list["ActivityLog"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    direct_reports: Mapped[list["EmployeeProfile"]] = relationship(
        foreign_keys="[EmployeeProfile.manager_id]",
        back_populates="manager",
        cascade="all, delete-orphan",
    )

    organization: Mapped["Organization | None"] = relationship(back_populates="users")

    __table_args__ = (
        Index("idx_users_deleted_at", "deleted_at", postgresql_where=text("deleted_at IS NOT NULL")),
        Index("idx_users_status", "status"),
        Index("idx_users_role", "role"),
        Index("idx_users_last_login_at", "last_login_at"),
        Index("idx_users_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


class StudentProfile(Base, UUIDPKMixin, TimestampMixin, SoftDeleteMixin, TenantMixin):
    __tablename__ = "student_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    nationality: Mapped[str | None] = mapped_column(String(100))
    passport_number: Mapped[str | None] = mapped_column(String(50))
    current_address: Mapped[str | None] = mapped_column(Text)

    education_level: Mapped[InstitutionType] = mapped_column(
        enum_type(InstitutionType, "institution_type", create_type=False),
        nullable=False,
    )
    university_name: Mapped[str | None] = mapped_column(String(255))
    institution_name: Mapped[str | None] = mapped_column(String(255))
    graduation_year: Mapped[int | None] = mapped_column(SmallInteger)
    gpa: Mapped[float | None] = mapped_column(Numeric(4, 2))

    preferred_country: Mapped[str | None] = mapped_column(String(100))
    preferred_program: Mapped[str | None] = mapped_column(String(255))
    preferred_intake: Mapped[str | None] = mapped_column(String(50))
    budget: Mapped[float | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)

    # Family & personal transparency details.
    father_name: Mapped[str | None] = mapped_column(String(150))
    mother_name: Mapped[str | None] = mapped_column(String(150))
    birth_place: Mapped[str | None] = mapped_column(String(150))
    permanent_address: Mapped[str | None] = mapped_column(Text)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(150))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20))

    user: Mapped[User] = relationship(back_populates="student_profile")
    english_tests: Mapped[list["StudentEnglishTest"]] = relationship(
        back_populates="student_profile",
        cascade="all, delete-orphan",
    )
    education_history: Mapped[list["StudentEducationHistory"]] = relationship(
        back_populates="student_profile",
        cascade="all, delete-orphan",
        order_by="StudentEducationHistory.end_date.desc()",
    )
    work_experience: Mapped[list["StudentWorkExperience"]] = relationship(
        back_populates="student_profile",
        cascade="all, delete-orphan",
        order_by="StudentWorkExperience.end_date.desc()",
    )

    __table_args__ = (
        Index("idx_student_profiles_user_id", "user_id"),
        Index("idx_student_profiles_deleted_at", "deleted_at", postgresql_where=text("deleted_at IS NOT NULL")),
        Index("idx_student_profiles_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<StudentProfile id={self.id} user_id={self.user_id}>"


class EmployeeProfile(Base, UUIDPKMixin, TimestampMixin, TenantMixin):
    __tablename__ = "employee_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    employee_code: Mapped[str | None] = mapped_column(String(50), unique=True)
    # Legacy free-text department — kept for backward compatibility with existing
    # rows. New writes go through department_id; department is a display fallback
    # only for profiles created before Department existed.
    department: Mapped[str | None] = mapped_column(String(100))
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
    )
    designation: Mapped[str | None] = mapped_column(String(100))
    # The structured counterpart to the free-text `designation` above — used
    # by the Duties module to resolve "everyone with this job role sees this
    # duty". Separate on purpose: designation is a display label with no
    # structure, job_role_id is a real FK an admin opts into per employee.
    job_role_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("job_roles.id", ondelete="SET NULL"),
    )
    joining_date: Mapped[date | None] = mapped_column(Date)
    employment_status: Mapped[str | None] = mapped_column(String(30), server_default="active")
    employment_type: Mapped[EmploymentType | None] = mapped_column(
        enum_type(EmploymentType, "employment_type", create_type=False)
    )
    # Legacy free-text office location — kept for backward compatibility with
    # existing rows. New writes go through office_id; office_location is a
    # display fallback only for profiles created before Office existed.
    office_location: Mapped[str | None] = mapped_column(String(255))
    office_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("offices.id", ondelete="SET NULL"),
    )
    probation_end_date: Mapped[date | None] = mapped_column(Date)
    contract_start_date: Mapped[date | None] = mapped_column(Date)
    contract_end_date: Mapped[date | None] = mapped_column(Date)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    user: Mapped[User] = relationship(
        back_populates="employee_profile",
        foreign_keys=[user_id],
    )
    manager: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[manager_id],
        back_populates="direct_reports",
        remote_side="User.id",
    )
    department_ref: Mapped["Department | None"] = relationship(
        "Department",
        foreign_keys=[department_id],
        back_populates="employee_profiles",
    )
    office: Mapped["Office | None"] = relationship(
        "Office",
        foreign_keys=[office_id],
        back_populates="employee_profiles",
    )
    job_role: Mapped["JobRole | None"] = relationship(
        "JobRole",
        foreign_keys=[job_role_id],
        back_populates="employee_profiles",
    )
    employment_events: Mapped[list["EmployeeEmploymentEvent"]] = relationship(
        back_populates="employee_profile",
        cascade="all, delete-orphan",
    )

    @property
    def department_name(self) -> str | None:
        """Requires department_ref to already be eager-loaded (see
        EmployeeProfileService) — never triggers a lazy load itself, which
        would raise under async SQLAlchemy outside a greenlet context."""
        return self.department_ref.name if self.department_ref is not None else self.department

    @property
    def office_name(self) -> str | None:
        """Requires office to already be eager-loaded, same rule as
        department_name above."""
        return self.office.name if self.office is not None else self.office_location

    @property
    def job_role_name(self) -> str | None:
        """Requires job_role to already be eager-loaded, same rule as
        department_name above."""
        return self.job_role.name if self.job_role is not None else None

    __table_args__ = (
        Index("idx_employee_profiles_user_id", "user_id"),
        Index("idx_employee_profiles_manager_id", "manager_id"),
        Index("idx_employee_profiles_department_id", "department_id"),
        Index("idx_employee_profiles_office_id", "office_id"),
        Index("idx_employee_profiles_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<EmployeeProfile id={self.id} employee_code={self.employee_code}>"
