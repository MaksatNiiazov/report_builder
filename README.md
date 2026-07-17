# TURKUAZ Report Builder

Внутренний сервис для запуска заранее подготовленных параметризованных `SELECT`-отчетов.

## Роли

- `report_builder_user`: видит опубликованные отчеты, задает значения параметров, запускает предпросмотр и выгружает CSV/XLSX.
- `report_builder_admin`: управляет источниками и SQL-шаблонами, публикует отчеты и читает журнал запусков.

Обычный пользователь не получает SQL-шаблон, DSN или административные API-операции.

## Структура

- FastAPI + SQLAlchemy + Alembic: `src/report_builder`.
- React + TypeScript + Vite + `@turkuaz/ui`: `frontend`.
- Служебная база хранит определения отчетов, зашифрованные DSN и журнал запусков.
- Целевые MSSQL и PostgreSQL базы подключаются отдельными read-only пользователями.
- Локальные порты: frontend `7505`, backend `8505`.

## Границы безопасности

Каждый запуск проходит все проверки:

1. Identity JWT и permission проверяются backend-сервисом.
2. Пользователь выбирает ID опубликованного отчета и передает только значения объявленных параметров.
3. SQL разбирается `sqlglot`: разрешен один `SELECT`/CTE, запрещены DDL, DML, `COPY`, команды и опасные функции.
4. Таблицы могут находиться только в разрешенных для источника схемах.
5. Значения передаются через SQLAlchemy bind parameters, а не подставляются в SQL строкой.
6. Запрос выполняется с ограничением времени, concurrency limit и внешним row limit. Для PostgreSQL дополнительно включается `READ ONLY` транзакция и `search_path`.
7. DSN шифруется Fernet-ключом. Значения параметров не пишутся в журнал.

AST-проверка является дополнительной защитой. Основная граница для данных — отдельная учетная запись MSSQL/PostgreSQL без прав записи.

## Подключение MSSQL

Для MSSQL используется SQLAlchemy URL с `pyodbc`, например:

```text
mssql+pyodbc://report_builder_ro:password@sql-host/app_database?driver=ODBC+Driver+18+for+SQL+Server
```

В контейнере установлен runtime `unixodbc`; Microsoft ODBC Driver 18 устанавливается на инфраструктурном образе отдельно. Разрешенная схема по умолчанию для MSSQL — `dbo`. Для PostgreSQL используется `postgresql+psycopg` и схема `public`.

## Read-only пользователь PostgreSQL

Выполнить от имени владельца нужной базы, заменив базу, схему и пароль:

```sql
CREATE ROLE report_builder_ro LOGIN PASSWORD 'replace-me' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CONNECT ON DATABASE app_database TO report_builder_ro;
GRANT USAGE ON SCHEMA public TO report_builder_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO report_builder_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO report_builder_ro;
ALTER ROLE report_builder_ro SET default_transaction_read_only = on;
ALTER ROLE report_builder_ro SET statement_timeout = '20s';
```

Эта роль не должна владеть базой, схемой или таблицами и не должна состоять в ролях с правами записи.

## Локальный запуск

```bash
cp .env.example .env
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/alembic upgrade head
.venv/bin/uvicorn report_builder.main:app --reload --port 8505
```

Во втором терминале:

```bash
cd frontend
npm install
npm run dev
```

- UI: `http://localhost:7505`
- Swagger: `http://localhost:8505/docs`
- Readiness: `http://localhost:8505/api/v1/ready`

Для полностью локальной UI-проверки можно временно установить `AUTH_ENABLED=false` для backend и `VITE_AUTH_DISABLED=true` для frontend. В production оба обхода должны быть отключены.

## Identity

Зарегистрировать сервис и две роли:

```bash
TOKEN='<identity-admin-token>' bash scripts/register_identity.sh
```

После назначения роли нужно заново войти, чтобы получить свежий JWT с новыми permissions.

## Docker

В `.env` обязательно задать стабильный `REPORT_SOURCE_ENCRYPTION_KEY`, затем:

```bash
docker compose up --build
```

## Проверка

```bash
.venv/bin/pytest
.venv/bin/ruff check src tests
cd frontend && npm run build
```
