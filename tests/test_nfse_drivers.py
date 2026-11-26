"""Drivers: roteamento por provedor, recusa com motivo e matriz de capacidade."""

from __future__ import annotations

import pytest
from app.nfse.drivers import (
    PENDENTES_LEGADO,
    ErroDeDriver,
    capacidade,
    exigir_implementacao,
    provedor_suportado,
)


class TestRoteamento:
    def test_nacional_e_suportado(self) -> None:
        assert provedor_suportado("nacional_rest") is True

    def test_abrasf_tem_motor_mas_nao_emite_sem_configuracao(self) -> None:
        # `provedor_suportado` responde "existe motor?"; emitir exige configuração do
        # município, verificada pela fábrica. As duas coisas são diferentes de propósito.
        assert provedor_suportado("ginfes") is True
        assert any(capacidade("ginfes").values()) is False

    def test_nacional_nao_levanta(self) -> None:
        exigir_implementacao("nacional_rest")  # não deve levantar

    def test_provedor_sem_motor_levanta_com_motivo(self) -> None:
        with pytest.raises(ErroDeDriver) as exc:
            exigir_implementacao("provedor_sem_motor")
        assert "provedor_sem_motor" in str(exc.value)
        assert exc.value.motivo.strip()

    def test_provedor_desconhecido_tambem_recusa(self) -> None:
        with pytest.raises(ErroDeDriver, match="desconhecido"):
            exigir_implementacao("provedor_que_nao_existe")

    def test_todo_pendente_tem_motivo_nao_vazio(self) -> None:
        # Motivo vazio seria o mesmo que "não sei"; o cadastro precisa dizer o que falta.
        assert all(m.strip() for m in PENDENTES_LEGADO.values())

    def test_matriz_marca_so_o_pronto_ponta_a_ponta(self) -> None:
        assert all(capacidade("nacional_rest").values())
        assert not any(capacidade("betha").values()), "motor sem config não emite"

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
