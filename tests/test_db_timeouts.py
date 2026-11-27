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


def _em_ms(valor: object) -> int:
    """Normaliza o que o Postgres devolve em `show statement_timeout` para milissegundos.

    O servidor escolhe a unidade mais legível: 60000 ms volta como "1min", 600000 como "10min".
    Comparar string aqui já quebrou uma vez — o teste certo compara o valor semântico.
    """
    texto = str(valor).strip()
    for sufixo, fator in (("min", 60_000), ("ms", 1), ("s", 1_000)):
        if texto.endswith(sufixo):
            return int(float(texto[: -len(sufixo)]) * fator)
    return int(texto)


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
        assert _em_ms(valor) == 9_000, valor


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
        assert _em_ms(valor) == 7_000, valor

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


class TestWorkerTemTetoProprio:
    """O worker **não** herda o teto de 60 s da API (§62).

    Motivo: um lote de emissões dura minutos. Se herdasse o teto da API, o lote seria abortado no
    meio e o estado ficaria parcial — documentos processados pela metade, sem erro claro para o
    cliente.
    """

    def test_configuracao_tem_teto_maior_que_a_api(self) -> None:
        conf = Settings(environment="test")

        assert conf.db_statement_timeout_worker_ms > conf.db_statement_timeout_ms

    async def test_engine_do_worker_aplica_o_teto_proprio(self, banco_limpo) -> None:
        from app.db import session as sessao_mod

        sessao_mod.reset_engine()
        try:
            fabrica = sessao_mod.obter_sessionmaker_worker()
            async with fabrica() as sessao:
                valor = await sessao.scalar(text("show statement_timeout"))
        finally:
            await sessao_mod.dispose_engine()

        assert valor is not None
        # 600 s = "10min" no formato do Postgres
        assert _em_ms(valor) == 600_000, valor

    async def test_engine_da_api_continua_com_o_teto_curto(self, banco_limpo) -> None:
        from app.db import session as sessao_mod

        sessao_mod.reset_engine()
        try:
            fabrica = sessao_mod.obter_sessionmaker()
            async with fabrica() as sessao:
                valor = await sessao.scalar(text("show statement_timeout"))
        finally:
            await sessao_mod.dispose_engine()

        assert valor is not None
        assert _em_ms(valor) == 60_000, valor
