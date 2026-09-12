"""ORM. One table per noun in the spec's data model.

Status and role fields are plain strings with CHECK constraints so the DB, not
just the code, refuses a bad value.
"""
from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBED_DIM = 768


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    brief: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    files: Mapped[list["SourceFile"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    participant_label: Mapped[str] = mapped_column(String(200))
    granted: Mapped[bool] = mapped_column(Boolean, default=True)
    scope_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SourceFile(Base):
    __tablename__ = "source_files"
    __table_args__ = (
        CheckConstraint("kind in ('audio','image','text','brief')", name="ck_kind"),
        CheckConstraint("level in (1,2,3)", name="ck_level"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    filename: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(10))
    level: Mapped[int] = mapped_column(Integer)
    level_confirmed_by_community: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_id: Mapped[int | None] = mapped_column(ForeignKey("consent_records.id"), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(Text)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    job: Mapped[Job] = relationship(back_populates="files")


class Segment(Base):
    __tablename__ = "segments"
    __table_args__ = (CheckConstraint("variant in ('with_wordlist','without')", name="ck_variant"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"))
    variant: Mapped[str] = mapped_column(String(20))
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    speaker: Mapped[str | None] = mapped_column(String(50), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    unsure: Mapped[bool] = mapped_column(Boolean, default=False)


class Artefact(Base):
    __tablename__ = "artefacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"))
    verbatim_text: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    illegible_count: Mapped[int] = mapped_column(Integer, default=0)
    maker_statement: Mapped[str] = mapped_column(Text, default="")


class Unit(Base):
    """A bit of material that can be quoted: a segment, an artefact line, a paragraph."""

    __tablename__ = "units"
    __table_args__ = (CheckConstraint("source_type in ('segment','artefact','text')", name="ck_source_type"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"))
    source_type: Mapped[str] = mapped_column(String(10))
    source_id: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    redacted_text: Mapped[str] = mapped_column(Text)
    speaker_key: Mapped[str] = mapped_column(String(100))
    level: Mapped[int] = mapped_column(Integer, default=1)
    embedding = mapped_column(Vector(EMBED_DIM), nullable=True)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)


THEME_STATUSES = ("draft", "unsupported", "confirmed", "fixed", "rejected", "added", "cut")


class Theme(Base):
    __tablename__ = "themes"
    __table_args__ = (
        CheckConstraint(f"status in {THEME_STATUSES}", name="ck_theme_status"),
        CheckConstraint("decided_by is null or decided_by in ('community','analyst')", name="ck_decided_by"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    label: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    decided_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    n_people: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    quotes: Mapped[list["ThemeQuote"]] = relationship(back_populates="theme", cascade="all, delete-orphan")


class ThemeQuote(Base):
    __tablename__ = "theme_quotes"
    id: Mapped[int] = mapped_column(primary_key=True)
    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"))

    theme: Mapped[Theme] = relationship(back_populates="quotes")
    unit: Mapped[Unit] = relationship()


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id"))
    actor_role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(20))
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class IdentifyFlag(Base):
    __tablename__ = "identify_flags"
    __table_args__ = (
        CheckConstraint("kind in ('small_n','pii')", name="ck_flag_kind"),
        CheckConstraint("decision is null or decision in ('keep','cut')", name="ck_flag_decision"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    theme_id: Mapped[int] = mapped_column(ForeignKey("themes.id"))
    kind: Mapped[str] = mapped_column(String(10))
    detail: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (CheckConstraint("kind in ('client','reportback')", name="ck_report_kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    kind: Mapped[str] = mapped_column(String(15))
    markdown: Mapped[str] = mapped_column(Text, default="")
    approved_community: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_analyst: Mapped[bool] = mapped_column(Boolean, default=False)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Concern(Base):
    __tablename__ = "concerns"
    __table_args__ = (
        CheckConstraint("category is null or category in ('harm','misuse','conduct','ai_error')", name="ck_concern_cat"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    stage: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(10), nullable=True)
    routed_to: Mapped[str] = mapped_column(String(200), default="")
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AICall(Base):
    """One row per model call. The §5 zero is `count(level = 3)` here."""

    __tablename__ = "ai_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer)
    stage: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(50))
    is_local: Mapped[bool] = mapped_column(Boolean)
    level: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
