FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends unixodbc \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY alembic ./alembic
RUN pip install --no-cache-dir .
RUN mkdir -p /app/data

EXPOSE 8505
CMD ["sh", "-c", "alembic upgrade head && uvicorn report_builder.main:app --host 0.0.0.0 --port 8505"]
