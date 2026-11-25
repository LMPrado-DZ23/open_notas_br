"""Fixtures compartilhadas.

Duas famílias convivem aqui:

- fixtures da biblioteca `notasbr` (auditoria de XML), que não tocam banco;
- fixtures da aplicação (Fase 1 em diante), que exigem PostgreSQL real.

O `PYTHONPATH` já é o `pyproject.toml` quem define (`pythonpath = ["src", "."]`).
"""

from __future__ import annotations

import os

import pytest

from tests import suporte
from tests.construir import cte, nfe

# ---------------------------------------------------------------------------
# Ambiente da aplicação — precisa acontecer ANTES de importar `app.*`, porque a
# configuração é lida no import e fica em cache por processo.
# ---------------------------------------------------------------------------
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = suporte.url_teste()
os.environ.setdefault("MASTER_ENCRYPTION_KEY", "")
os.environ["LOG_JSON"] = "false"
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("ADMIN_API_TOKEN", "")


# ---------------------------------------------------------------------------
# Fixtures da biblioteca notasbr
# ---------------------------------------------------------------------------
@pytest.fixture
def xml_nfe() -> bytes:
    """NF-e 4.00 sintética e autoconsistente (só o aviso ASSIN-005 é esperado)."""
    return nfe()


@pytest.fixture
def xml_cte() -> bytes:
    """CT-e 4.00 sintético e autoconsistente."""
    return cte()


# ---------------------------------------------------------------------------
# Fixtures da aplicação
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def banco_teste() -> str:
    """Banco de teste criado e migrado. Pula a suíte se não houver PostgreSQL."""
    if not suporte.banco_disponivel():
        pytest.skip(
            "PostgreSQL indisponível em "
            f"{suporte.url_admin()!r}; suba com `docker compose up -d postgres` "
            "ou aponte TEST_DATABASE_URL para um banco acessível"
        )
    suporte.provisionar_banco()
    return suporte.url_teste()


@pytest.fixture
async def banco_limpo(banco_teste: str) -> str:
    """Garante schema migrado e tabelas vazias antes de cada teste.

    O engine é descartado **antes e depois** do teste, no mesmo event loop que o
    usou. Sem isso, o pool do teste anterior fica ligado a um loop já fechado e o
    asyncpg estoura `RuntimeError: Event loop is closed` no teardown — cada teste
    tem o próprio loop.
    """
    from app.db.session import dispose_engine, reset_engine

    await dispose_engine()
    reset_engine()
    await suporte.limpar_tabelas(banco_teste)
    yield banco_teste
    await dispose_engine()
    reset_engine()


@pytest.fixture
async def sessao_db(banco_limpo: str):
    """Sessão assíncrona direta, para testes de repositório e serviço."""
    from app.db.session import obter_sessionmaker

    fabrica = obter_sessionmaker()
    async with fabrica() as sessao:
        yield sessao


@pytest.fixture
def app_teste(banco_limpo: str):
    """Instância do app por teste, permitindo `dependency_overrides` isolado."""
    from app.main import criar_app

    return criar_app()


@pytest.fixture
async def cliente(app_teste):
    """Cliente HTTP ligado ao app ASGI, sem abrir porta."""
    from httpx import ASGITransport, AsyncClient

    transporte = ASGITransport(app=app_teste)
    async with AsyncClient(transport=transporte, base_url="http://test") as http:
        yield http
