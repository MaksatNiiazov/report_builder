import pytest

from report_builder.execution import QueryExecutionError, coerce_parameters
from report_builder.sql_security import (
    UnsafeQueryError,
    inspect_select_query,
    validate_parameter_definitions,
)


def test_accepts_parameterized_select_and_collects_tables() -> None:
    inspection = inspect_select_query(
        "SELECT id, total FROM public.orders WHERE created_at >= :date_from",
        ["public"],
    )
    assert inspection.parameters == {"date_from"}
    assert inspection.tables == {"public.orders"}


def test_accepts_mssql_select_with_dbo_schema() -> None:
    inspection = inspect_select_query(
        "SELECT TOP 10 id FROM dbo.orders WHERE created_at >= :date_from",
        ["dbo"],
        engine="mssql",
    )
    assert inspection.parameters == {"date_from"}
    assert inspection.tables == {"dbo.orders"}


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM public.orders",
        "UPDATE public.orders SET total = 0",
        "DROP TABLE public.orders",
        "SELECT 1; SELECT 2",
        "COPY public.orders TO '/tmp/orders.csv'",
        "SELECT pg_sleep(10)",
        "SELECT private_function(id) FROM public.orders",
    ],
)
def test_rejects_unsafe_queries(query: str) -> None:
    with pytest.raises(UnsafeQueryError):
        inspect_select_query(query, ["public"])


def test_rejects_unapproved_schema() -> None:
    with pytest.raises(UnsafeQueryError, match="Schema is not allowed"):
        inspect_select_query("SELECT * FROM private.payroll", ["public"])


def test_cte_name_is_not_treated_as_schema_table() -> None:
    inspection = inspect_select_query(
        "WITH recent AS (SELECT * FROM public.orders) SELECT * FROM recent",
        ["public"],
    )
    assert inspection.tables == {"public.orders"}


def test_parameter_definitions_must_match_placeholders() -> None:
    with pytest.raises(UnsafeQueryError, match="Missing parameter definitions"):
        validate_parameter_definitions([], {"date_from"})
    with pytest.raises(UnsafeQueryError, match="Unused parameter definitions"):
        validate_parameter_definitions(
            [{"name": "unused", "label": "Unused", "type": "text"}], set()
        )


def test_parameter_like_text_in_literals_and_comments_is_ignored() -> None:
    inspection = inspect_select_query("SELECT ':literal' AS value -- :comment", ["public"])
    assert inspection.parameters == set()


def test_parameter_values_are_typed_and_unknown_values_rejected() -> None:
    definitions = [
        {"name": "count", "label": "Count", "type": "integer", "required": True},
        {"name": "enabled", "label": "Enabled", "type": "boolean", "required": True},
    ]
    assert coerce_parameters(definitions, {"count": "12", "enabled": "true"}) == {
        "count": 12,
        "enabled": True,
    }
    with pytest.raises(QueryExecutionError, match="Неизвестные параметры"):
        coerce_parameters(definitions, {"count": 12, "enabled": True, "sql": "DROP"})
