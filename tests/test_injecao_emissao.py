"""Emissão sob circuito: chave correta, bloqueio antes da chamada e isolamento."""

from __future__ import annotations

import pytest
from app.core.circuit import CircuitoAberto, Estado
from app.nfse.injecao import chave_da_emissao, descrever, emitir_com_circuito
from app.nfse.resiliencia import RegistroCircuitos


def registro(limite: int = 2) -> RegistroCircuitos:
    return RegistroCircuitos(limite_falhas=limite, espera_s=30.0)


class TestChave:
    def test_chave_usa_uf_e_autorizacao(self) -> None:
        assert chave_da_emissao("go") == "sefaz:GO:autorizacao"

    def test_ufs_diferentes_chaves_diferentes(self) -> None:
        assert chave_da_emissao("GO") != chave_da_emissao("SP")


class TestExecucao:
    async def test_sucesso_retorna_o_resultado(self) -> None:
        async def acao() -> str:
            return "autorizada"

        assert await emitir_com_circuito(registro(), uf="GO", acao=acao) == "autorizada"

    async def test_circuito_aberto_nao_chama_o_servico(self) -> None:
        r = registro(limite=1)
        executou = False

        async def falha() -> str:
            raise ConnectionError("SEFAZ fora")

        async def nao_devia() -> str:
            nonlocal executou
            executou = True
            return "x"

        with pytest.raises(ConnectionError):
            await emitir_com_circuito(r, uf="GO", acao=falha)

        with pytest.raises(CircuitoAberto):
            await emitir_com_circuito(r, uf="GO", acao=nao_devia)
        assert executou is False, "circuito aberto não pode chamar o serviço"

    async def test_rejeicao_fiscal_propaga_sem_abrir(self) -> None:
        r = registro(limite=1)

        async def rejeita() -> str:
            raise ValueError("rejeição 539")

        for _ in range(3):
            with pytest.raises(ValueError):
                await emitir_com_circuito(r, uf="GO", acao=rejeita)
        assert r.obter(chave_da_emissao("GO")).estado is Estado.FECHADO


class TestIsolamento:
    async def test_queda_em_go_nao_afeta_sp(self) -> None:
        r = registro(limite=1)

        async def falha() -> str:
            raise ConnectionError("SEFAZ GO fora")

        async def ok() -> str:
            return "autorizada"

        with pytest.raises(ConnectionError):
            await emitir_com_circuito(r, uf="GO", acao=falha)

        assert await emitir_com_circuito(r, uf="SP", acao=ok) == "autorizada"
        assert descrever(r, "GO", "SP") == {"GO": "aberto", "SP": "fechado"}

    async def test_uf_sem_uso_aparece_como_inexistente(self) -> None:
        assert descrever(registro(), "MG") == {"MG": "inexistente"}
