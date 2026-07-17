from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from report_builder.auth import get_identity_claims
from report_builder.crypto import encrypt_secret
from report_builder.db import Base, get_db
from report_builder.main import app
from report_builder.models import DataSource, Report


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSession() as db:
        source = DataSource(
            name="Test Source",
            engine="postgresql",
            encrypted_dsn=encrypt_secret("postgresql+psycopg://readonly:test@localhost/test"),
            allowed_schemas=["public"],
            is_active=True,
        )
        db.add(source)
        db.flush()
        db.add_all(
            [
                Report(
                    slug="published",
                    name="Published",
                    data_source_id=source.id,
                    query_template="SELECT id FROM public.orders",
                    parameters=[],
                    default_row_limit=100,
                    max_row_limit=1000,
                    is_published=True,
                ),
                Report(
                    slug="draft",
                    name="Draft",
                    data_source_id=source.id,
                    query_template="SELECT secret FROM public.internal_orders",
                    parameters=[],
                    default_row_limit=100,
                    max_row_limit=1000,
                    is_published=False,
                ),
            ]
        )
        db.commit()

    def override_db() -> Iterator[Session]:
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def test_missing_token_is_unauthorized(client: TestClient) -> None:
    response = client.get("/api/v1/reports")
    assert response.status_code == 401


def test_user_sees_only_published_metadata_and_never_sql(client: TestClient) -> None:
    app.dependency_overrides[get_identity_claims] = lambda: {
        "email": "user@example.com",
        "permissions": ["report_builder.reports.read", "report_builder.reports.execute"],
    }
    response = client.get("/api/v1/reports")
    assert response.status_code == 200
    assert [item["slug"] for item in response.json()] == ["published"]
    assert "query_template" not in response.json()[0]


def test_user_cannot_open_admin_report_or_sources(client: TestClient) -> None:
    app.dependency_overrides[get_identity_claims] = lambda: {
        "email": "user@example.com",
        "permissions": ["report_builder.reports.read", "report_builder.reports.execute"],
    }
    assert client.get("/api/v1/admin/reports/1").status_code == 403
    assert client.get("/api/v1/admin/sources").status_code == 403


def test_admin_can_read_draft_sql_but_source_response_has_no_dsn(client: TestClient) -> None:
    app.dependency_overrides[get_identity_claims] = lambda: {
        "email": "admin@example.com",
        "permissions": ["*"],
    }
    report_response = client.get("/api/v1/admin/reports/2")
    source_response = client.get("/api/v1/admin/sources")
    assert report_response.status_code == 200
    assert report_response.json()["query_template"].startswith("SELECT secret")
    assert source_response.status_code == 200
    assert "dsn" not in source_response.json()[0]
    assert "encrypted_dsn" not in source_response.json()[0]

