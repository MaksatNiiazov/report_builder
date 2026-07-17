from __future__ import annotations

import re
from dataclasses import dataclass

from sqlglot import exp, parse
from sqlglot.errors import ParseError

SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

FORBIDDEN_NODES = (
    exp.Alter,
    exp.Command,
    exp.Commit,
    exp.Copy,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Execute,
    exp.Grant,
    exp.Insert,
    exp.Into,
    exp.Lock,
    exp.Merge,
    exp.Rollback,
    exp.Set,
    exp.Transaction,
    exp.TruncateTable,
    exp.Update,
)

FORBIDDEN_FUNCTIONS = {
    "dblink",
    "dblink_connect",
    "lo_export",
    "lo_import",
    "pg_advisory_lock",
    "pg_advisory_unlock",
    "pg_cancel_backend",
    "pg_notify",
    "pg_read_binary_file",
    "pg_read_file",
    "pg_sleep",
    "pg_terminate_backend",
    "query_to_xml",
    "set_config",
    "openrowset",
    "opendatasource",
    "xp_cmdshell",
    "xp_regread",
}

ALLOWED_ANONYMOUS_FUNCTIONS = {
    "json_agg",
    "json_build_array",
    "json_build_object",
    "json_object_agg",
    "jsonb_agg",
    "jsonb_build_array",
    "jsonb_build_object",
    "jsonb_object_agg",
}

ALLOWED_MSSQL_ANONYMOUS_FUNCTIONS = {
    "coalesce",
    "dateadd",
    "datediff",
    "datename",
    "datepart",
    "getdate",
    "isnull",
    "try_convert",
    "try_cast",
}


class UnsafeQueryError(ValueError):
    pass


@dataclass(frozen=True)
class QueryInspection:
    parameters: set[str]
    schemas: set[str]
    tables: set[str]


def inspect_select_query(
    sql: str,
    allowed_schemas: list[str],
    engine: str = "postgresql",
) -> QueryInspection:
    text = sql.strip()
    if not text:
        raise UnsafeQueryError("SQL query is required")
    if len(text) > 100_000:
        raise UnsafeQueryError("SQL query is too large")
    try:
        dialect = "tsql" if engine == "mssql" else "postgres"
        statements = [statement for statement in parse(text, read=dialect) if statement is not None]
    except ParseError as exc:
        raise UnsafeQueryError(f"SQL parse error: {exc}") from exc
    if len(statements) != 1:
        raise UnsafeQueryError("Exactly one SQL statement is allowed")

    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise UnsafeQueryError("Only SELECT queries and CTEs are allowed")
    forbidden = next(statement.find_all(FORBIDDEN_NODES), None)
    if forbidden is not None:
        raise UnsafeQueryError(f"Forbidden SQL operation: {forbidden.key.upper()}")

    cte_names = {
        cte.alias_or_name.casefold()
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }
    normalized_allowed = {schema.casefold() for schema in allowed_schemas}
    default_schema = "dbo" if engine == "mssql" else "public"
    schemas: set[str] = set()
    tables: set[str] = set()
    for table in statement.find_all(exp.Table):
        table_name = table.name
        if not table_name or table_name.casefold() in cte_names:
            continue
        schema = table.db or default_schema
        if schema.casefold() not in normalized_allowed:
            raise UnsafeQueryError(f"Schema is not allowed: {schema}")
        schemas.add(schema)
        tables.add(f"{schema}.{table_name}")

    for function in statement.find_all(exp.Func):
        name = (
            function.name.casefold()
            if isinstance(function, exp.Anonymous)
            else function.sql_name().casefold()
        )
        if name in FORBIDDEN_FUNCTIONS:
            raise UnsafeQueryError(f"Function is not allowed: {name}")
        allowed_functions = ALLOWED_ANONYMOUS_FUNCTIONS
        if engine == "mssql":
            allowed_functions = allowed_functions | ALLOWED_MSSQL_ANONYMOUS_FUNCTIONS
        if isinstance(function, exp.Anonymous) and name not in allowed_functions:
            raise UnsafeQueryError(f"Custom or unsupported function is not allowed: {name}")

    parameters = {
        placeholder.name
        for placeholder in statement.find_all(exp.Placeholder)
        if placeholder.name
    }
    if any(name.startswith("report_") for name in parameters):
        raise UnsafeQueryError("Parameter names starting with report_ are reserved")
    return QueryInspection(parameters=parameters, schemas=schemas, tables=tables)


def validate_parameter_definitions(
    definitions: list[dict[str, object]],
    query_parameters: set[str],
) -> None:
    names: list[str] = []
    for definition in definitions:
        name = definition.get("name")
        if not isinstance(name, str) or not SAFE_IDENTIFIER_PATTERN.fullmatch(name):
            raise UnsafeQueryError("Every parameter needs a safe name")
        if name.startswith("report_"):
            raise UnsafeQueryError("Parameter names starting with report_ are reserved")
        names.append(name)
    if len(names) != len(set(names)):
        raise UnsafeQueryError("Parameter names must be unique")
    defined = set(names)
    missing = query_parameters - defined
    unused = defined - query_parameters
    if missing:
        raise UnsafeQueryError(f"Missing parameter definitions: {', '.join(sorted(missing))}")
    if unused:
        raise UnsafeQueryError(f"Unused parameter definitions: {', '.join(sorted(unused))}")


def strip_trailing_semicolon(sql: str) -> str:
    return sql.strip().removesuffix(";").rstrip()
