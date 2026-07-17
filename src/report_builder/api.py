from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, joinedload

from .auth import (
    AUDIT_READ,
    REPORT_EXECUTE,
    REPORT_MANAGE,
    REPORT_READ,
    SOURCE_MANAGE,
    actor_from_claims,
    get_identity_claims,
    has_permission,
    require_permission,
)
from .config import settings
from .crypto import decrypt_secret, encrypt_secret
from .db import get_db
from .execution import (
    QueryExecutionError,
    QueryResult,
    csv_bytes,
    execute_report,
    test_data_source,
    xlsx_bytes,
)
from .models import DataSource, Report, ReportExecution
from .schemas import (
    DataSourceCreate,
    DataSourceResponse,
    DataSourceUpdate,
    ExecutionResponse,
    PreviewResponse,
    QueryValidationResponse,
    ReportAdminDetail,
    ReportParameter,
    ReportSummary,
    ReportUpdate,
    ReportWrite,
    RunRequest,
)
from .sql_security import (
    SAFE_IDENTIFIER_PATTERN,
    UnsafeQueryError,
    inspect_select_query,
    validate_parameter_definitions,
)

router = APIRouter()
Claims = Annotated[dict[str, Any], Depends(get_identity_claims)]
Db = Annotated[Session, Depends(get_db)]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "report-builder"}


@router.get("/ready")
def ready(db: Db) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Metadata database is unavailable") from exc
    return {"status": "ready", "service": "report-builder"}


@router.get("/me")
def me(claims: Claims) -> dict[str, Any]:
    return {
        "email": claims.get("email") or claims.get("sub"),
        "full_name": claims.get("full_name") or claims.get("name") or claims.get("email"),
        "roles": claims.get("roles", []),
        "permissions": claims.get("permissions", []),
        "can_manage_reports": has_permission(claims, REPORT_MANAGE),
        "can_manage_sources": has_permission(claims, SOURCE_MANAGE),
        "can_read_audit": has_permission(claims, AUDIT_READ),
    }


@router.get("/reports", response_model=list[ReportSummary])
def list_reports(
    db: Db,
    claims: Annotated[dict[str, Any], Depends(require_permission(REPORT_READ))],
    search: str = Query(default="", max_length=160),
) -> list[ReportSummary]:
    statement = select(Report).options(joinedload(Report.data_source)).order_by(Report.name)
    if not has_permission(claims, REPORT_MANAGE):
        statement = statement.where(Report.is_published.is_(True))
    if search.strip():
        statement = statement.where(Report.name.ilike(f"%{search.strip()}%"))
    return [_report_summary(report) for report in db.scalars(statement)]


@router.get("/reports/{report_id}", response_model=ReportSummary)
def get_report(
    report_id: int,
    db: Db,
    claims: Annotated[dict[str, Any], Depends(require_permission(REPORT_READ))],
) -> ReportSummary:
    report = _get_report(db, report_id)
    if not report.is_published and not has_permission(claims, REPORT_MANAGE):
        raise HTTPException(status_code=404, detail="Report not found")
    return _report_summary(report)


@router.post("/reports/{report_id}/preview", response_model=PreviewResponse)
def preview_report(
    report_id: int,
    payload: RunRequest,
    db: Db,
    claims: Annotated[dict[str, Any], Depends(require_permission(REPORT_EXECUTE))],
) -> PreviewResponse:
    report = _get_report(db, report_id)
    if not report.is_published and not has_permission(claims, REPORT_MANAGE):
        raise HTTPException(status_code=404, detail="Report not found")
    limit = min(payload.row_limit or settings.preview_row_limit, settings.preview_row_limit)
    result = _execute_and_audit(db, report, claims, payload.parameters, limit, "preview")
    return PreviewResponse(
        columns=result.columns,
        rows=result.rows,
        row_count=len(result.rows),
        truncated=result.truncated,
        duration_ms=result.duration_ms,
    )


@router.post("/reports/{report_id}/export")
def export_report(
    report_id: int,
    payload: RunRequest,
    db: Db,
    claims: Annotated[dict[str, Any], Depends(require_permission(REPORT_EXECUTE))],
    format: Literal["csv", "xlsx"] = Query(default="xlsx"),
) -> Response:
    report = _get_report(db, report_id)
    if not report.is_published and not has_permission(claims, REPORT_MANAGE):
        raise HTTPException(status_code=404, detail="Report not found")
    limit = payload.row_limit or report.default_row_limit
    result = _execute_and_audit(db, report, claims, payload.parameters, limit, format)
    if format == "csv":
        content = csv_bytes(result)
        media_type = "text/csv; charset=utf-8"
    else:
        content = xlsx_bytes(result)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    filename = f"{report.slug}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.{format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/admin/sources", response_model=list[DataSourceResponse])
def list_sources(
    db: Db,
    _claims: Annotated[dict[str, Any], Depends(require_permission(SOURCE_MANAGE))],
) -> list[DataSourceResponse]:
    return [_source_response(source) for source in db.scalars(select(DataSource).order_by(DataSource.name))]


@router.post("/admin/sources", response_model=DataSourceResponse, status_code=201)
def create_source(
    payload: DataSourceCreate,
    db: Db,
    _claims: Annotated[dict[str, Any], Depends(require_permission(SOURCE_MANAGE))],
) -> DataSourceResponse:
    dsn = payload.dsn.get_secret_value()
    engine = _validate_source(dsn, payload.allowed_schemas, payload.engine)
    source = DataSource(
        name=payload.name.strip(),
        engine=engine,
        encrypted_dsn=encrypt_secret(dsn),
        allowed_schemas=payload.allowed_schemas,
        is_active=payload.is_active,
    )
    db.add(source)
    _commit_or_conflict(db, "Источник с таким названием уже существует")
    db.refresh(source)
    return _source_response(source)


@router.patch("/admin/sources/{source_id}", response_model=DataSourceResponse)
def update_source(
    source_id: int,
    payload: DataSourceUpdate,
    db: Db,
    _claims: Annotated[dict[str, Any], Depends(require_permission(SOURCE_MANAGE))],
) -> DataSourceResponse:
    source = _get_source(db, source_id)
    values = payload.model_dump(exclude_unset=True)
    dsn_secret = values.pop("dsn", None)
    dsn = dsn_secret.get_secret_value() if dsn_secret else decrypt_secret(source.encrypted_dsn)
    schemas = values.get("allowed_schemas", source.allowed_schemas)
    engine = _validate_source(dsn, schemas, values.get("engine", source.engine))
    for key, value in values.items():
        setattr(source, key, value.strip() if key == "name" else value)
    source.engine = engine
    if dsn_secret:
        source.encrypted_dsn = encrypt_secret(dsn)
    _commit_or_conflict(db, "Источник с таким названием уже существует")
    db.refresh(source)
    return _source_response(source)


@router.post("/admin/sources/{source_id}/test")
def check_source(
    source_id: int,
    db: Db,
    _claims: Annotated[dict[str, Any], Depends(require_permission(SOURCE_MANAGE))],
) -> dict[str, str]:
    source = _get_source(db, source_id)
    try:
        test_data_source(source)
    except QueryExecutionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok", "message": "Read-only подключение работает"}


@router.get("/admin/reports/{report_id}", response_model=ReportAdminDetail)
def get_admin_report(
    report_id: int,
    db: Db,
    _claims: Annotated[dict[str, Any], Depends(require_permission(REPORT_MANAGE))],
) -> ReportAdminDetail:
    return _admin_report(_get_report(db, report_id))


@router.post("/admin/reports", response_model=ReportAdminDetail, status_code=201)
def create_report(
    payload: ReportWrite,
    db: Db,
    claims: Annotated[dict[str, Any], Depends(require_permission(REPORT_MANAGE))],
) -> ReportAdminDetail:
    source = _get_source(db, payload.data_source_id)
    _validate_report(payload.query_template, payload.parameters, source)
    if payload.max_row_limit > settings.absolute_row_limit:
        raise HTTPException(status_code=422, detail="Row limit exceeds service policy")
    actor = actor_from_claims(claims)
    report = Report(
        **payload.model_dump(mode="json"),
        created_by=actor,
        updated_by=actor,
    )
    db.add(report)
    _commit_or_conflict(db, "Отчет с таким кодом уже существует")
    return _admin_report(_get_report(db, report.id))


@router.patch("/admin/reports/{report_id}", response_model=ReportAdminDetail)
def update_report(
    report_id: int,
    payload: ReportUpdate,
    db: Db,
    claims: Annotated[dict[str, Any], Depends(require_permission(REPORT_MANAGE))],
) -> ReportAdminDetail:
    report = _get_report(db, report_id)
    values = payload.model_dump(exclude_unset=True, mode="json")
    merged = ReportWrite.model_validate(
        {
            "slug": values.get("slug", report.slug),
            "name": values.get("name", report.name),
            "description": values.get("description", report.description),
            "data_source_id": values.get("data_source_id", report.data_source_id),
            "query_template": values.get("query_template", report.query_template),
            "parameters": values.get("parameters", report.parameters),
            "default_row_limit": values.get("default_row_limit", report.default_row_limit),
            "max_row_limit": values.get("max_row_limit", report.max_row_limit),
            "is_published": values.get("is_published", report.is_published),
        }
    )
    source = _get_source(db, merged.data_source_id)
    _validate_report(merged.query_template, merged.parameters, source)
    if merged.max_row_limit > settings.absolute_row_limit:
        raise HTTPException(status_code=422, detail="Row limit exceeds service policy")
    for key, value in merged.model_dump(mode="json").items():
        setattr(report, key, value)
    report.updated_by = actor_from_claims(claims)
    _commit_or_conflict(db, "Отчет с таким кодом уже существует")
    return _admin_report(_get_report(db, report.id))


@router.post("/admin/reports/{report_id}/validate", response_model=QueryValidationResponse)
def validate_report(
    report_id: int,
    db: Db,
    _claims: Annotated[dict[str, Any], Depends(require_permission(REPORT_MANAGE))],
) -> QueryValidationResponse:
    report = _get_report(db, report_id)
    try:
        inspection = inspect_select_query(
            report.query_template, report.data_source.allowed_schemas, report.data_source.engine
        )
        validate_parameter_definitions(report.parameters, inspection.parameters)
    except UnsafeQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return QueryValidationResponse(
        valid=True,
        parameters=sorted(inspection.parameters),
        schemas=sorted(inspection.schemas),
        tables=sorted(inspection.tables),
    )


@router.get("/admin/executions", response_model=list[ExecutionResponse])
def list_executions(
    db: Db,
    _claims: Annotated[dict[str, Any], Depends(require_permission(AUDIT_READ))],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ExecutionResponse]:
    statement = (
        select(ReportExecution)
        .options(joinedload(ReportExecution.report))
        .order_by(ReportExecution.started_at.desc())
        .limit(limit)
    )
    return [
        ExecutionResponse(
            id=item.id,
            report_id=item.report_id,
            report_name=item.report.name,
            actor=item.actor,
            output_format=item.output_format,
            status=item.status,
            row_count=item.row_count,
            duration_ms=item.duration_ms,
            error_code=item.error_code,
            started_at=item.started_at,
        )
        for item in db.scalars(statement)
    ]


def _execute_and_audit(
    db: Session,
    report: Report,
    claims: dict[str, Any],
    parameters: dict[str, Any],
    limit: int,
    output_format: str,
) -> QueryResult:
    execution = ReportExecution(
        report_id=report.id,
        actor=actor_from_claims(claims),
        output_format=output_format,
        status="running",
    )
    db.add(execution)
    db.commit()
    try:
        result = execute_report(report, parameters, limit)
        execution.status = "success"
        execution.row_count = len(result.rows)
        execution.duration_ms = result.duration_ms
        db.commit()
        return result
    except QueryExecutionError as exc:
        execution.status = "error"
        execution.error_code = exc.code
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _get_source(db: Session, source_id: int) -> DataSource:
    source = db.get(DataSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    return source


def _get_report(db: Session, report_id: int) -> Report:
    statement = (
        select(Report).options(joinedload(Report.data_source)).where(Report.id == report_id)
    )
    report = db.scalar(statement)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _validate_report(
    query_template: str,
    parameters: list[ReportParameter],
    source: DataSource,
) -> None:
    try:
        inspection = inspect_select_query(query_template, source.allowed_schemas, source.engine)
        validate_parameter_definitions(
            [parameter.model_dump(mode="json") for parameter in parameters], inspection.parameters
        )
    except UnsafeQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _validate_source(dsn: str, allowed_schemas: list[str], engine: str) -> str:
    try:
        url = make_url(dsn)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid database connection URL") from exc
    if url.drivername.startswith("postgresql"):
        detected_engine = "postgresql"
    elif url.drivername.startswith("mssql"):
        detected_engine = "mssql"
    else:
        raise HTTPException(status_code=422, detail="Supported sources are MSSQL and PostgreSQL")
    if engine != detected_engine:
        raise HTTPException(status_code=422, detail="Engine does not match the connection URL")
    if not url.host or not url.database:
        raise HTTPException(status_code=422, detail="Database host and name are required")
    invalid_schemas = [name for name in allowed_schemas if not SAFE_IDENTIFIER_PATTERN.fullmatch(name)]
    if invalid_schemas:
        raise HTTPException(status_code=422, detail="Allowed schemas contain invalid names")
    return detected_engine


def _source_response(source: DataSource) -> DataSourceResponse:
    url = make_url(decrypt_secret(source.encrypted_dsn))
    default_port = 1433 if source.engine == "mssql" else 5432
    target = f"{url.host or '-'}:{url.port or default_port}/{url.database or '-'}"
    return DataSourceResponse(
        id=source.id,
        name=source.name,
        engine=source.engine,
        target=target,
        allowed_schemas=source.allowed_schemas,
        is_active=source.is_active,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def _report_summary(report: Report) -> ReportSummary:
    return ReportSummary(
        id=report.id,
        slug=report.slug,
        name=report.name,
        description=report.description,
        parameters=[ReportParameter.model_validate(item) for item in report.parameters],
        default_row_limit=report.default_row_limit,
        max_row_limit=report.max_row_limit,
        is_published=report.is_published,
        data_source_name=report.data_source.name,
        updated_at=report.updated_at,
    )


def _admin_report(report: Report) -> ReportAdminDetail:
    summary = _report_summary(report)
    return ReportAdminDetail(
        **summary.model_dump(),
        data_source_id=report.data_source_id,
        query_template=report.query_template,
        created_by=report.created_by,
        updated_by=report.updated_by,
        created_at=report.created_at,
    )


def _commit_or_conflict(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
