from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, model_validator


ParameterType = Literal["text", "integer", "decimal", "date", "datetime", "boolean"]
DataSourceEngine = Literal["mssql", "postgresql"]


class ReportParameter(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=80)
    label: str = Field(min_length=1, max_length=120)
    type: ParameterType = "text"
    required: bool = True
    default: Any | None = None
    placeholder: str | None = Field(default=None, max_length=160)


class DataSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    engine: DataSourceEngine = "postgresql"
    dsn: SecretStr
    allowed_schemas: list[str] = Field(default_factory=lambda: ["public"], min_length=1)
    is_active: bool = True


class DataSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    engine: DataSourceEngine | None = None
    dsn: SecretStr | None = None
    allowed_schemas: list[str] | None = Field(default=None, min_length=1)
    is_active: bool | None = None


class DataSourceResponse(BaseModel):
    id: int
    name: str
    engine: str
    target: str
    allowed_schemas: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ReportWrite(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)
    data_source_id: int
    query_template: str = Field(min_length=1, max_length=100_000)
    parameters: list[ReportParameter] = Field(default_factory=list)
    default_row_limit: int = Field(default=1_000, ge=1, le=50_000)
    max_row_limit: int = Field(default=10_000, ge=1, le=50_000)
    is_published: bool = False

    @model_validator(mode="after")
    def validate_limits(self) -> ReportWrite:
        if self.default_row_limit > self.max_row_limit:
            raise ValueError("default_row_limit cannot exceed max_row_limit")
        return self


class ReportUpdate(BaseModel):
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)
    data_source_id: int | None = None
    query_template: str | None = Field(default=None, min_length=1, max_length=100_000)
    parameters: list[ReportParameter] | None = None
    default_row_limit: int | None = Field(default=None, ge=1, le=50_000)
    max_row_limit: int | None = Field(default=None, ge=1, le=50_000)
    is_published: bool | None = None


class ReportSummary(BaseModel):
    id: int
    slug: str
    name: str
    description: str | None
    parameters: list[ReportParameter]
    default_row_limit: int
    max_row_limit: int
    is_published: bool
    data_source_name: str
    updated_at: datetime


class ReportAdminDetail(ReportSummary):
    data_source_id: int
    query_template: str
    created_by: str | None
    updated_by: str | None
    created_at: datetime


class RunRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    row_limit: int | None = Field(default=None, ge=1, le=50_000)


class PreviewResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: int


class QueryValidationResponse(BaseModel):
    valid: bool
    parameters: list[str]
    schemas: list[str]
    tables: list[str]


class ExecutionResponse(BaseModel):
    id: int
    report_id: int
    report_name: str
    actor: str | None
    output_format: str
    status: str
    row_count: int | None
    duration_ms: int | None
    error_code: str | None
    started_at: datetime
