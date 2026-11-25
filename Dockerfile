# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# curl é usado pelo healthcheck do compose; o resto é biblioteca de runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Dependências primeiro (camada de cache): copia só o manifesto.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY app ./app

RUN pip install --upgrade pip \
    && pip install ".[app]"

COPY alembic.ini ./
COPY alembic ./alembic

# Executa como usuário sem privilégio.
RUN useradd --create-home --uid 1000 notasbr \
    && chown -R notasbr:notasbr /srv
USER notasbr

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
