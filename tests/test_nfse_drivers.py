"""Drivers: roteamento por provedor, recusa com motivo e matriz de capacidade."""

from __future__ import annotations

import pytest
from app.nfse.drivers import (
    PENDENTES,
    ErroDeDriver,
    capacidade,
    exigir_implementacao,
    provedor_suportado,
)


class TestRoteamento:
    def test_nacional_e_suportado(self) -> None:
        assert provedor_suportado("nacional_rest") is True

    def test_todos_os_outros_do_cadastro_nao_sao(self) -> None:
        # A coluna `provedor` do cadastro tem 17 valores; 16 não têm driver.
        assert provedor_suportado("ginfes") is False
        assert provedor_suportado("abrasf_2_04") is False
        assert provedor_suportado("goiania") is False

    def test_nacional_nao_levanta(self) -> None:
        exigir_implementacao("nacional_rest")  # não deve levantar

    def test_pendente_levanta_com_motivo_factual(self) -> None:
        with pytest.raises(ErroDeDriver) as exc:
            exigir_implementacao("ginfes")
        assert "ginfes" in str(exc.value)
        assert "encoding" in exc.value.motivo or "URL" in exc.value.motivo

    def test_provedor_desconhecido_tambem_recusa(self) -> None:
        with pytest.raises(ErroDeDriver, match="desconhecido"):
            exigir_implementacao("provedor_que_nao_existe")

    def test_todo_pendente_tem_motivo_nao_vazio(self) -> None:
        # Motivo vazio seria o mesmo que "não sei"; o cadastro precisa dizer o que falta.
        assert all(m.strip() for m in PENDENTES.values())

    def test_matriz_marca_so_o_suportado(self) -> None:
        assert all(capacidade("nacional_rest").values())
        assert not any(capacidade("betha").values())

    def test_matriz_tem_todas_as_operacoes(self) -> None:
        esperado = {
            "emitir",
            "consultar_lote",
            "consultar_por_rps",
            "cancelar",
            "consultar_tomadas",
            "testar_conectividade",
        }
        assert set(capacidade("nacional_rest")) == esperado


class TestContrato:
    def test_resultado_normalizado_tem_os_campos(self) -> None:
        from app.nfse.drivers import CategoriaErro, ResultadoDriver

        ok = ResultadoDriver(sucesso=True, protocolo="123", numero_nfse="456")
        assert ok.protocolo == "123"
        assert ok.erro_categoria is None

        falha = ResultadoDriver(sucesso=False, codigo="E10", erro_categoria=CategoriaErro.MUNICIPIO)
        assert falha.erro_categoria is CategoriaErro.MUNICIPIO

    def test_categoria_espelha_rfc7807(self) -> None:
        from app.core.errors import OrigemErro
        from app.nfse.drivers import CategoriaErro

        for nome in ("SEFAZ", "MUNICIPIO", "VALIDACAO", "INTERNO"):
            assert CategoriaErro(nome) is not None
            assert OrigemErro(nome) is not None
