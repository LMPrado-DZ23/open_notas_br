"""Apoio à suíte de testes: provisionamento do banco de teste.

Estratégia: os testes de integração rodam contra um PostgreSQL **real**, criado
neste módulo e migrado com `alembic upgrade head`. Testar contra SQLite
esconderia diferenças que só aparecem no banco de produção (JSONB, `now()`,
constraint nomeada, `ON DELETE CASCADE`), e testar com `create_all` deixaria a
migração sem cobertura — que é justamente o artefato que roda em produção.

Quando o PostgreSQL não está acessível, os testes de integração são pulados com
motivo explícito, nunca silenciosamente aprovados.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Banco administrativo de onde o banco de teste é criado.
DB_ADMIN_PADRAO = "postgresql+asyncpg://notasbr:notasbr@127.0.0.1:55434/notasbr"
NOME_BANCO_TESTE = "notasbr_test"

TABELAS = (
    "invoice_events",
    "fiscal_documents",
    "invoices",
    "tenant_certificates",
    "tenant_fiscal_configs",
    "tax_assessments",
    "batch_jobs",
    "webhook_deliveries",
    "tenants",
)


def url_admin() -> str:
    """URL do banco administrativo (sem o banco de teste)."""
    return os.environ.get("TEST_DATABASE_URL") or DB_ADMIN_PADRAO


def url_teste() -> str:
    """URL do banco de teste, com o banco trocado por `notasbr_test`."""
    bruta = url_admin()
    base = bruta.rsplit("/", 1)[0]
    return f"{base}/{NOME_BANCO_TESTE}"


def dsn_asyncpg(url: str) -> str:
    """Converte a URL do SQLAlchemy no DSN que o asyncpg entende."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _criar_banco() -> None:
    import asyncpg

    conexao = await asyncpg.connect(dsn=dsn_asyncpg(url_admin()), timeout=5)
    try:
        existe = await conexao.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", NOME_BANCO_TESTE
        )
        if not existe:
            # CREATE DATABASE não roda dentro de transação.
            await conexao.execute(f'CREATE DATABASE "{NOME_BANCO_TESTE}"')
    finally:
        await conexao.close()


def banco_disponivel() -> bool:
    """True se o PostgreSQL responde.

    Usa a própria conexão administrativa porque é a que o provisionamento exige.
    """
    import asyncpg

    async def _probe() -> bool:
        try:
            conexao = await asyncpg.connect(dsn=dsn_asyncpg(url_admin()), timeout=5)
        except Exception:
            return False
        try:
            return await conexao.fetchval("SELECT 1") == 1
        finally:
            await conexao.close()

    try:
        return asyncio.run(_probe())
    except Exception:
        return False


def provisionar_banco() -> None:
    """Cria o banco de teste e aplica todas as migrações.

    Síncrono de propósito: roda como fixture de sessão sem depender de event loop
    de teste, evitando conflito de escopo de loop.
    """
    asyncio.run(_criar_banco())

    ambiente = {
        **os.environ,
        "DATABASE_URL": url_teste(),
        "ENVIRONMENT": "test",
        "MASTER_ENCRYPTION_KEY": "",
        "LOG_LEVEL": "WARNING",
    }
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=RAIZ,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            "falha ao aplicar migrações no banco de teste:\n"
            f"stdout: {resultado.stdout}\nstderr: {resultado.stderr}"
        )


async def limpar_tabelas(url: str) -> None:
    """Zera todas as tabelas entre testes, preservando o schema migrado."""
    import asyncpg

    conexao = await asyncpg.connect(dsn=dsn_asyncpg(url), timeout=10)
    try:
        await conexao.execute(
            "TRUNCATE TABLE " + ", ".join(f'"{t}"' for t in TABELAS) + " RESTART IDENTITY CASCADE"
        )
    finally:
        await conexao.close()
