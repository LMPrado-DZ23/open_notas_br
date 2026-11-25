"""Ambiente de migração do Alembic (assíncrono).

A URL vem de `Settings.database_url`, nunca do `alembic.ini`: assim existe uma
única fonte de verdade para conexão e nenhum segredo em arquivo versionado.
"""

from __future__ import annotations

import asyncio
import contextlib
from logging.config import fileConfig

# Importar os modelos é o que popula `Base.metadata`. Sem este import, o
# autogenerate enxerga um banco vazio e propõe derrubar tabelas existentes.
import app.db.models  # noqa: F401
from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config
target_metadata = Base.metadata

if config.config_file_name is not None:
    with contextlib.suppress(KeyError):  # ini sem secoes de log
        fileConfig(config.config_file_name, disable_existing_loggers=False)


def obter_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Gera o SQL sem abrir conexão (`alembic upgrade head --sql`)."""
    context.configure(
        url=obter_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(obter_url(), poolclass=pool.NullPool)
    try:
        async with engine.connect() as conexao:
            await conexao.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
