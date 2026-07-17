from sqlalchemy.exc import DBAPIError

from report_builder.execution import _database_error, _wrap_mssql_query


def test_mssql_order_by_is_valid_inside_limited_wrapper() -> None:
    wrapped = _wrap_mssql_query(
        "SELECT id, name FROM dbo.items ORDER BY name",
        101,
    )

    assert "SELECT TOP 101" in wrapped
    assert "ORDER BY name OFFSET 0 ROWS" in wrapped


def test_mssql_query_without_order_by_is_not_changed() -> None:
    wrapped = _wrap_mssql_query("SELECT id FROM dbo.items", 11)

    assert "SELECT id FROM dbo.items" in wrapped
    assert "OFFSET 0 ROWS" not in wrapped


def test_database_error_explains_missing_column() -> None:
    original = Exception("[42S22] Invalid column name 'missing_column'.")
    error = DBAPIError.instance(
        statement="SELECT missing_column FROM dbo.items",
        params=None,
        orig=original,
        dbapi_base_err=Exception,
    )

    code, message = _database_error(error)

    assert code == "database_error"
    assert "Столбец не найден" in message
    assert "missing_column" in message


def test_database_error_hides_password() -> None:
    original = Exception("Login failed; PWD=super-secret; password=another-secret")
    error = DBAPIError.instance(
        statement="SELECT 1",
        params=None,
        orig=original,
        dbapi_base_err=Exception,
    )

    _, message = _database_error(error)

    assert "super-secret" not in message
    assert "another-secret" not in message
