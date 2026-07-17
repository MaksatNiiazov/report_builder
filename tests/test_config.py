from report_builder.config import Settings


def test_cors_origins_accept_compose_csv_environment(monkeypatch) -> None:
    monkeypatch.setenv(
        "BACKEND_CORS_ORIGINS",
        "http://localhost:7505,http://127.0.0.1:7505",
    )

    settings = Settings(_env_file=None)

    assert settings.backend_cors_origins == [
        "http://localhost:7505",
        "http://127.0.0.1:7505",
    ]
