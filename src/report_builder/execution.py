from __future__ import annotations

import csv
import threading
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from time import monotonic
from typing import Any

from openpyxl import Workbook
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from .config import settings
from .crypto import decrypt_secret
from .models import DataSource, Report
from .schemas import ReportParameter
from .sql_security import inspect_select_query, strip_trailing_semicolon


class QueryExecutionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    duration_ms: int
    truncated: bool


query_slots = threading.BoundedSemaphore(value=settings.max_concurrent_queries)


def execute_report(report: Report, raw_values: dict[str, Any], requested_limit: int) -> QueryResult:
    source = report.data_source
    if not source.is_active:
        raise QueryExecutionError("source_inactive", "Источник данных отключен")
    inspect_select_query(report.query_template, source.allowed_schemas, source.engine)
    values = coerce_parameters(report.parameters, raw_values)
    limit = min(requested_limit, report.max_row_limit, settings.absolute_row_limit)
    if not query_slots.acquire(blocking=False):
        raise QueryExecutionError("capacity_exceeded", "Сервис занят. Повторите запрос позже")
    started = monotonic()
    target_engine = None
    try:
        target_engine = create_engine(
            decrypt_secret(source.encrypted_dsn),
            poolclass=NullPool,
            connect_args=_connect_args(source),
        )
        inner_sql = strip_trailing_semicolon(report.query_template)
        if source.engine == "mssql":
            wrapped_sql = f"SELECT TOP {limit + 1} * FROM (\n{inner_sql}\n) AS report_result"
        else:
            wrapped_sql = f"SELECT * FROM (\n{inner_sql}\n) AS report_result LIMIT :report_row_limit"
        with target_engine.connect() as connection:
            if source.engine == "mssql":
                # pyodbc applies this timeout to each command on the raw connection.
                connection.connection.driver_connection.timeout = settings.query_timeout_seconds
            transaction = connection.begin()
            try:
                if source.engine == "postgresql":
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                    connection.exec_driver_sql(
                        f"SET LOCAL statement_timeout = {settings.query_timeout_seconds * 1000}"
                    )
                    schemas = ", ".join(f'"{schema}"' for schema in source.allowed_schemas)
                    connection.exec_driver_sql(f"SET LOCAL search_path TO {schemas}, pg_catalog")
                result = connection.execute(
                    text(wrapped_sql),
                    {**values, "report_row_limit": limit + 1},
                )
                columns = _unique_columns(list(result.keys()))
                raw_rows = result.fetchmany(limit + 1)
            finally:
                transaction.rollback()
        truncated = len(raw_rows) > limit
        rows = [[_serializable(value) for value in row] for row in raw_rows[:limit]]
        return QueryResult(
            columns=columns,
            rows=rows,
            duration_ms=round((monotonic() - started) * 1000),
            truncated=truncated,
        )
    except QueryExecutionError:
        raise
    except DBAPIError as exc:
        code = "query_timeout" if "statement timeout" in str(exc).lower() else "database_error"
        message = (
            "Превышено время выполнения отчета"
            if code == "query_timeout"
            else "База данных отклонила запрос отчета"
        )
        raise QueryExecutionError(code, message) from exc
    except SQLAlchemyError as exc:
        raise QueryExecutionError("connection_error", "Не удалось подключиться к источнику") from exc
    finally:
        if target_engine is not None:
            target_engine.dispose()
        query_slots.release()


def test_data_source(source: DataSource) -> None:
    target_engine = create_engine(
        decrypt_secret(source.encrypted_dsn),
        poolclass=NullPool,
        connect_args=_connect_args(source),
    )
    try:
        with target_engine.connect() as connection:
            transaction = connection.begin()
            try:
                if source.engine == "postgresql":
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                connection.exec_driver_sql("SELECT 1")
            finally:
                transaction.rollback()
    except SQLAlchemyError as exc:
        raise QueryExecutionError("connection_error", "Не удалось подключиться к источнику") from exc
    finally:
        target_engine.dispose()


def _connect_args(source: DataSource) -> dict[str, int]:
    timeout = min(settings.query_timeout_seconds, 10)
    return {"connect_timeout": timeout} if source.engine == "postgresql" else {"timeout": timeout}


def coerce_parameters(
    definitions: list[dict[str, object]],
    values: dict[str, Any],
) -> dict[str, Any]:
    allowed_names = {str(item["name"]) for item in definitions}
    unexpected = set(values) - allowed_names
    if unexpected:
        raise QueryExecutionError(
            "invalid_parameters", f"Неизвестные параметры: {', '.join(sorted(unexpected))}"
        )
    coerced: dict[str, Any] = {}
    for raw_definition in definitions:
        definition = ReportParameter.model_validate(raw_definition)
        value = values.get(definition.name, definition.default)
        if value in (None, ""):
            if definition.required:
                raise QueryExecutionError(
                    "invalid_parameters", f"Параметр обязателен: {definition.label}"
                )
            coerced[definition.name] = None
            continue
        try:
            coerced[definition.name] = _coerce_value(definition.type, value)
        except (TypeError, ValueError, InvalidOperation) as exc:
            raise QueryExecutionError(
                "invalid_parameters", f"Неверное значение параметра: {definition.label}"
            ) from exc
    return coerced


def _coerce_value(parameter_type: str, value: Any) -> Any:
    if parameter_type == "text":
        return str(value)
    if parameter_type == "integer":
        return int(value)
    if parameter_type == "decimal":
        return Decimal(str(value))
    if parameter_type == "date":
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    if parameter_type == "datetime":
        return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parameter_type == "boolean":
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().casefold()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        raise ValueError("Invalid boolean")
    raise ValueError("Unsupported parameter type")


def csv_bytes(result: QueryResult) -> bytes:
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(result.columns)
    writer.writerows(result.rows)
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def xlsx_bytes(result: QueryResult) -> bytes:
    workbook = Workbook(write_only=True)
    worksheet = workbook.create_sheet("Отчет")
    worksheet.append(result.columns)
    for row in result.rows:
        worksheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _serializable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def _unique_columns(columns: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    result: list[str] = []
    for column in columns:
        counts[column] = counts.get(column, 0) + 1
        result.append(column if counts[column] == 1 else f"{column}_{counts[column]}")
    return result
