"""Tempos do banco aplicados **no servidor** (§60).

Por que testar isto no servidor e não no objeto do engine: `connect_args` "parece certo" mesmo
quando o asyncpg ignora a chave. A prova é perguntar ao Postgres qual valor ele está usando.

E por que importa: sem `statement_timeout` no servidor, um timeout de cliente só desiste de
esperar — o Postgres continua executando e segurando a conexão. Com pool de 10, dez consultas
travadas derrubam a API inteira.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


class TestConfiguracao:
    def test_valores_padrao_sao_folgado_mas_finitos(self) -> None:
        conf = Settings(environment="test")

        assert 1_000 <= conf.db_statement_timeout_ms <= 600_000
        assert conf.db_idle_tx_timeout_ms >= conf.db_statement_timeout_ms
        assert conf.db_pool_recycle_s > 0

    async def test_criar_engine_aplica_o_valor_configurado(self, banco_limpo) -> None:
        """O caminho de produção é `criar_engine`, não `create_async_engine` direto.

        Este teste existe porque a primeira versão verificava o `_creator` do pool por introspecção
        — o que "parece certo" sem provar nada. Perguntar ao servidor é a única prova de que a
        configuração sai do arquivo e chega no Postgres.
        """
        from app.db.session import criar_engine

        engine = criar_engine(Settings(environment="test", db_statement_timeout_ms=9_000))
        try:
            async with engine.connect() as conexao:
                valor = await conexao.scalar(text("show statement_timeout"))
        finally:
            await engine.dispose()

        assert valor is not None
        assert "9s" in str(valor) or "9000" in str(valor), valor


class TestNoServidor:
    """Prova que o Postgres **aplica** o valor, não que o Python passou o argumento."""

    async def test_statement_timeout_chega_ao_servidor(self, banco_limpo) -> None:
        engine = create_async_engine(
            Settings(environment="test").database_url,
            connect_args={"server_settings": {"statement_timeout": "7000"}},
        )
        try:
            async with engine.connect() as conexao:
                valor = await conexao.scalar(text("show statement_timeout"))
        finally:
            await engine.dispose()

        # O Postgres devolve com unidade ("7s") ou o número cru, conforme a versão.
        assert valor is not None
        assert "7s" in str(valor) or "7000" in str(valor), valor

    async def test_consulta_lenta_e_cancelada_pelo_servidor(self, banco_limpo) -> None:
        """Com teto de 200 ms, um `pg_sleep` de 1 s tem de falhar — não esperar."""
        engine = create_async_engine(
            Settings(environment="test").database_url,
            connect_args={"server_settings": {"statement_timeout": "200"}},
        )
        try:
            async with engine.connect() as conexao:
                with pytest.raises(Exception) as erro:
                    await conexao.execute(text("select pg_sleep(1)"))
        finally:
            await engine.dispose()

        # QueryCanceled do Postgres, embrulhado pelo driver.
        assert "cancel" in str(erro.value).lower() or "timeout" in str(erro.value).lower()
