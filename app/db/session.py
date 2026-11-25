"""Engine e sessão assíncronas do SQLAlchemy.

O engine é criado sob demanda e pode ser descartado, para que a suíte de testes
possa reapontar o `DATABASE_URL` entre execuções sem reiniciar o processo.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def criar_engine(settings: Settings | None = None) -> AsyncEngine:
    """Cria um engine novo a partir da configuração."""
    conf = settings or get_settings()
    return create_async_engine(
        conf.database_url,
        echo=conf.db_echo,
        pool_size=conf.db_pool_size,
        max_overflow=conf.db_max_overflow,
        pool_pre_ping=True,
        future=True,
    )


def obter_engine() -> AsyncEngine:
    """Engine do processo (criado na primeira chamada)."""
    global _engine
    if _engine is None:
        _engine = criar_engine()
        logger.debug("engine_criado")
    return _engine


def obter_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Fábrica de sessões ligada ao engine do processo."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=obter_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependência do FastAPI: uma sessão por requisição.

    Faz `rollback` automático em exceção e sempre fecha a sessão, mesmo que o
    handler levante erro antes do commit.
    """
    fabrica = obter_sessionmaker()
    sessao = fabrica()
    try:
        yield sessao
    except Exception:
        await sessao.rollback()
        raise
    finally:
        await sessao.close()


async def dispose_engine() -> None:
    """Fecha o pool. Chamado no shutdown da aplicação."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        logger.debug("engine_descartado")
    _engine = None
    _sessionmaker = None


def reset_engine() -> None:
    """Esquece o engine sem fechar (uso em teste que troca de banco)."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None


async def ping() -> bool:
    """True se o banco responde a um `SELECT 1`."""
    from sqlalchemy import text

    try:
        async with obter_engine().connect() as conexao:
            resultado = await conexao.execute(text("SELECT 1"))
            return resultado.scalar_one() == 1
    except Exception as exc:
        logger.warning("banco_indisponivel", extra={"erro": str(exc)})
        return False
