from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from ..db.mixins import TimestampMixin, UUIDPKMixin
from ..db.types import enum_type
from .enums import DegreeLevel


class Country(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "countries"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    iso2: Mapped[str] = mapped_column(String(2), nullable=False, unique=True)
    iso3: Mapped[str | None] = mapped_column(String(3), unique=True)
    phone_code: Mapped[str | None] = mapped_column(String(10))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    flag_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    universities: Mapped[list["University"]] = relationship(
        back_populates="country",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("idx_countries_name", "name"),)

    def __repr__(self) -> str:
        return f"<Country id={self.id} name={self.name}>"


class University(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "universities"

    country_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("countries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    logo_url: Mapped[str | None] = mapped_column(Text)
    ranking: Mapped[int | None] = mapped_column(Integer)
    is_partner: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    country: Mapped[Country] = relationship(back_populates="universities")
    programs: Mapped[list["Program"]] = relationship(
        back_populates="university",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_universities_country_id", "country_id"),
        Index("idx_universities_name", "name"),
        Index("idx_universities_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<University id={self.id} name={self.name}>"


class Program(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "programs"

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("universities.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    degree_level: Mapped[DegreeLevel | None] = mapped_column(
        enum_type(DegreeLevel, "degree_level", create_type=False)
    )
    field_of_study: Mapped[str | None] = mapped_column(String(100))
    duration_months: Mapped[int | None] = mapped_column(SmallInteger)
    tuition_fee: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    intake: Mapped[str | None] = mapped_column(String(50))
    minimum_gpa: Mapped[float | None] = mapped_column(Numeric(4, 2))
    minimum_ielts: Mapped[float | None] = mapped_column(Numeric(3, 1))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    university: Mapped[University] = relationship(back_populates="programs")
    intakes: Mapped[list["Intake"]] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
    )
    applications: Mapped[list["Application"]] = relationship(back_populates="program")

    __table_args__ = (
        Index("idx_programs_university_id", "university_id"),
        Index("idx_programs_name", "name"),
        Index("idx_programs_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Program id={self.id} name={self.name}>"


class Intake(Base, UUIDPKMixin):
    __tablename__ = "intakes"

    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    application_deadline: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    program: Mapped[Program] = relationship(back_populates="intakes")
    applications: Mapped[list["Application"]] = relationship(back_populates="intake")

    __table_args__ = (
        Index("idx_intakes_program_id", "program_id"),
        Index("idx_intakes_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Intake id={self.id} name={self.name}>"
