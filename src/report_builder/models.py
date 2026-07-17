from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataSource(Base):
    __tablename__ = "report_data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    engine: Mapped[str] = mapped_column(String(30), default="postgresql")
    encrypted_dsn: Mapped[str] = mapped_column(Text)
    allowed_schemas: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["public"])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    reports: Mapped[list[Report]] = relationship(back_populates="data_source")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("report_data_sources.id"), index=True)
    query_template: Mapped[str] = mapped_column(Text)
    parameters: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    default_row_limit: Mapped[int] = mapped_column(Integer, default=1_000)
    max_row_limit: Mapped[int] = mapped_column(Integer, default=10_000)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[str | None] = mapped_column(String(255))
    updated_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    data_source: Mapped[DataSource] = relationship(back_populates="reports")
    executions: Mapped[list[ReportExecution]] = relationship(back_populates="report")


class ReportExecution(Base):
    __tablename__ = "report_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), index=True)
    actor: Mapped[str | None] = mapped_column(String(255), index=True)
    output_format: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True)
    row_count: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    report: Mapped[Report] = relationship(back_populates="executions")

