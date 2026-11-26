"""Cria o banco usado pela checagem de migrations, se ainda não existir.

Existe para que `alembic check` rode em CI sem depender do banco de testes (que a suíte cria e
derruba a cada execução). Idempotente: rodar duas vezes não falha.
"""

from __future__ import annotations

import asyncio
import os
import sys

import asyncpg

#: Banco dedicado à checagem de migrations. Separado do `notasbr_test` de propósito: a suíte
#: apaga aquele banco entre execuções, e a checagem precisa de um schema estável em `head`.
NOME = os.environ.get("BANCO_MIGRACOES", "notasbr_migracoes")


def _dsn_administrativo() -> str:
    """DSN do banco `postgres`, derivado de `TEST_DATABASE_URL`/`DATABASE_URL`."""
    bruto = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    if not bruto:
        raise SystemExit("defina TEST_DATABASE_URL ou DATABASE_URL")
    base, _, _ = bruto.partition("?")
    return base.rsplit("/", 1)[0] + "/postgres"


async def criar() -> bool:
    conexao = await asyncpg.connect(_dsn_administrativo().replace("+asyncpg", ""))
    try:
        existe = await conexao.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", NOME)
        if existe:
            return False
        # `CREATE DATABASE` não aceita parâmetro; o nome vem de constante controlada.
        await conexao.execute(f'CREATE DATABASE "{NOME}"')
        return True
    finally:
        await conexao.close()


def main() -> int:
    criado = asyncio.run(criar())
    print(f"banco {NOME}: {'criado' if criado else 'já existia'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
