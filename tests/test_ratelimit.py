"""Rate limit por tenant: janela, bloqueio, isolamento e falha aberta."""

from __future__ import annotations

import pytest
from app.core.ratelimit import ArmazenamentoMemoria, Limitador, ResultadoLimite


class TestJanela:
    async def test_permite_ate_o_limite(self) -> None:
        lim = Limitador(ArmazenamentoMemoria(), limite=3, janela_s=60)
        resultados = [await lim.verificar("t1") for _ in range(3)]
        assert all(r.permitido for r in resultados)
        assert [r.restante for r in resultados] == [2, 1, 0]

    async def test_bloqueia_acima_do_limite(self) -> None:
        lim = Limitador(ArmazenamentoMemoria(), limite=2, janela_s=60)
        await lim.verificar("t1")
        await lim.verificar("t1")
        terceira = await lim.verificar("t1")
        assert terceira.permitido is False
        assert terceira.restante == 0

    async def test_retry_after_aponta_a_janela(self) -> None:
        lim = Limitador(ArmazenamentoMemoria(), limite=1, janela_s=30)
        await lim.verificar("t1")
        bloqueio = await lim.verificar("t1")
        assert bloqueio.cabecalhos()["Retry-After"] == "30"


class TestIsolamento:
    async def test_tenants_nao_compartilham_cota(self) -> None:
        lim = Limitador(ArmazenamentoMemoria(), limite=1, janela_s=60)
        assert (await lim.verificar("t1")).permitido is True
        # Outro tenant tem cota própria: o limite é por lojista, não global.
        assert (await lim.verificar("t2")).permitido is True
        assert (await lim.verificar("t1")).permitido is False


class TestCusto:
    async def test_custo_alto_consome_varios(self) -> None:
        lim = Limitador(ArmazenamentoMemoria(), limite=5, janela_s=60)
        r = await lim.verificar("t1", custo=4)
        assert r.total == 4
        assert r.restante == 1

    async def test_custo_zero_recusado(self) -> None:
        lim = Limitador(ArmazenamentoMemoria(), limite=5)
        with pytest.raises(ValueError):
            await lim.verificar("t1", custo=0)


class TestFalhaAberta:
    async def test_storage_fora_do_ar_permite(self) -> None:
        class Quebrado:
            async def incrementar(self, chave: str, ttl_s: int) -> int:
                raise RuntimeError("redis fora")

            async def consultar(self, chave: str) -> int:
                raise RuntimeError("redis fora")

        # Em sistema fiscal, ficar sem atender é pior que atender acima da cota.
        resultado = await Limitador(Quebrado(), limite=1).verificar("t1")
        assert resultado.permitido is True
        assert resultado.restante == 1


class TestConfiguracao:
    def test_limite_invalido(self) -> None:
        with pytest.raises(ValueError, match="limite"):
            Limitador(ArmazenamentoMemoria(), limite=0)

    def test_janela_invalida(self) -> None:
        with pytest.raises(ValueError, match="janela"):
            Limitador(ArmazenamentoMemoria(), janela_s=0)

    def test_cabecalhos_de_sucesso(self) -> None:
        r = ResultadoLimite(permitido=True, total=1, limite=60, restante=59, retry_after_s=0)
        cab = r.cabecalhos()
        assert cab["X-RateLimit-Limit"] == "60"
        assert cab["X-RateLimit-Remaining"] == "59"
        assert "Retry-After" not in cab


class TestMemoria:
    async def test_consulta_nao_incrementa(self) -> None:
        store = ArmazenamentoMemoria()
        await store.incrementar("k", 60)
        assert await store.consultar("k") == 1
        assert await store.consultar("k") == 1

    async def test_ttl_nao_afeta_consulta_imediata(self) -> None:
        store = ArmazenamentoMemoria()
        assert await store.consultar("inexistente") == 0
