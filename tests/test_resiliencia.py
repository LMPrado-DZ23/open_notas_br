"""Registro de circuitos e execução protegida."""

from __future__ import annotations

import asyncio

import pytest
from app.core.circuit import CircuitoAberto, Estado
from app.nfse.resiliencia import (
    RegistroCircuitos,
    chave_municipio,
    chave_sefaz,
    executar,
)


def registro(limite: int = 3) -> RegistroCircuitos:
    return RegistroCircuitos(limite_falhas=limite, espera_s=30.0)


async def falha_transitoria() -> str:
    raise ConnectionError("SEFAZ fora do ar")


async def rejeicao_fiscal() -> str:
    raise ValueError("rejeição 539")


class TestExecucao:
    async def test_sucesso_passa_e_fecha(self) -> None:
        r = registro()

        async def ok() -> str:
            return "autorizada"

        assert await executar(r, chave_sefaz("GO", "autorizacao"), ok) == "autorizada"
        assert r.obter(chave_sefaz("GO", "autorizacao")).estado is Estado.FECHADO

    async def test_falha_transitoria_propaga(self) -> None:
        r = registro()
        with pytest.raises(ConnectionError):
            await executar(r, chave_sefaz("GO", "autorizacao"), falha_transitoria)

    async def test_abre_apos_o_limite(self) -> None:
        r = registro(limite=2)
        chave = chave_sefaz("GO", "autorizacao")
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await executar(r, chave, falha_transitoria)
        assert r.obter(chave).estado is Estado.ABERTO

    async def test_aberto_nao_chama_o_servico(self) -> None:
        r = registro(limite=1)
        chave = chave_sefaz("GO", "autorizacao")
        with pytest.raises(ConnectionError):
            await executar(r, chave, falha_transitoria)

        chamou = False

        async def nao_devia() -> str:
            nonlocal chamou
            chamou = True
            return "x"

        # Circuito aberto levanta SEM executar: é o ponto de existir o circuito.
        with pytest.raises(CircuitoAberto):
            await executar(r, chave, nao_devia)
        assert chamou is False

    async def test_rejeicao_fiscal_nao_abre(self) -> None:
        r = registro(limite=1)
        chave = chave_sefaz("GO", "autorizacao")
        for _ in range(3):
            with pytest.raises(ValueError):
                await executar(r, chave, rejeicao_fiscal)
        # Serviço no ar e respondendo: abrir por erro nosso pararia de emitir.
        assert r.obter(chave).estado is Estado.FECHADO

    async def test_timeout_e_transitorio(self) -> None:
        r = registro(limite=1)

        async def estoura() -> str:
            raise TimeoutError

        with pytest.raises(asyncio.TimeoutError):
            await executar(r, chave_sefaz("GO", "status"), estoura)
        assert r.obter(chave_sefaz("GO", "status")).estado is Estado.ABERTO


class TestIsolamento:
    async def test_ufs_diferentes_nao_se_afetam(self) -> None:
        r = registro(limite=1)
        go = chave_sefaz("GO", "autorizacao")
        sp = chave_sefaz("SP", "autorizacao")

        with pytest.raises(ConnectionError):
            await executar(r, go, falha_transitoria)
        assert r.obter(go).estado is Estado.ABERTO
        assert r.obter(sp).estado is Estado.FECHADO

    async def test_municipios_diferentes_nao_se_afetam(self) -> None:
        r = registro(limite=1)
        with pytest.raises(ConnectionError):
            await executar(r, chave_municipio("5200258", "emitir"), falha_transitoria)
        assert r.obter(chave_municipio("3550308", "emitir")).estado is Estado.FECHADO

    async def test_sefaz_e_municipio_sao_circuitos_distintos(self) -> None:
        r = registro(limite=1)
        with pytest.raises(ConnectionError):
            await executar(r, chave_sefaz("GO", "autorizacao"), falha_transitoria)
        assert r.obter(chave_municipio("5200258", "emitir")).estado is Estado.FECHADO


class TestObservabilidade:
    async def test_estados_para_metrica(self) -> None:
        r = registro(limite=1)
        with pytest.raises(ConnectionError):
            await executar(r, chave_sefaz("GO", "autorizacao"), falha_transitoria)
        estados = r.estados()
        assert estados[chave_sefaz("GO", "autorizacao")] == Estado.ABERTO

    def test_resetar_por_chave(self) -> None:
        r = registro()
        r.obter("x")
        r.resetar("x")
        assert r.estados()["x"] == Estado.FECHADO
