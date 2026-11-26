"""Laudo construído a partir da emissão: conteúdo e determinismo."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.tax.integracao_emissao import da_emissao

EMITENTE = {"uf": "GO", "municipio_ibge": "5200258", "regime": "1"}
SERVICO = {"valor": "100.00", "aliquota": "0.05", "codigo_tributacao_nacional": "010501"}
RESULTADO = {"valor_iss": "5.00", "aliquota": "5.00"}
TOMADOR = {"documento": "11222333000181"}


def montar(**extra):
    base = dict(
        emitente=EMITENTE,
        tomador=TOMADOR,
        servico=SERVICO,
        resultado=RESULTADO,
        data_emissao=date(2026, 11, 25),
        trace_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
    )
    base.update(extra)
    return da_emissao(**base)


class TestConteudo:
    def test_entrada_tem_o_que_influencia_o_tributo(self) -> None:
        laudo = montar()
        assert laudo.entrada["municipio_ibge"] == "5200258"
        assert laudo.entrada["aliquota"] == Decimal("0.05")
        assert laudo.entrada["base_calculo"] == Decimal("100.00")
        assert laudo.entrada["tomador_pj"] is True

    def test_saida_tem_o_tributo(self) -> None:
        laudo = montar()
        assert laudo.saida["valor_iss"] == Decimal("5.00")
        assert laudo.saida["iss_retido"] is False

    def test_trace_id_e_o_id_da_fatura(self) -> None:
        laudo = montar()
        assert laudo.trace_id == "11111111-1111-1111-1111-111111111111"

    def test_sem_tomador_nao_quebra(self) -> None:
        laudo = montar(tomador=None)
        assert laudo.entrada["tomador_pj"] is False

    def test_valor_invalido_vira_none_em_vez_de_explodir(self) -> None:
        # Não inventar número: campo ilegível fica None e aparece como ausente.
        laudo = montar(servico={"valor": "abc"})
        assert laudo.entrada["base_calculo"] is None

    def test_regime_vem_do_emitente(self) -> None:
        laudo = montar(emitente={"uf": "GO", "op_simp_nac": "1"})
        assert laudo.entrada["regime"] == "1"

    def test_regras_e_tabelas_entram_no_laudo(self) -> None:
        from app.tax.auditoria import TabelaConsultada

        laudo = montar(
            regras=("ISS 5%",),
            tabelas=(TabelaConsultada("iss", "2026.1", date(2026, 1, 1)),),
        )
        assert laudo.regras == ("ISS 5%",)
        assert laudo.tabelas[0].versao == "2026.1"


class TestDeterminismo:
    def test_mesma_emissao_mesmo_laudo(self) -> None:
        assert montar().hash_laudo == montar().hash_laudo

    def test_aliquota_diferente_muda_o_laudo(self) -> None:
        a = montar()
        b = montar(servico={**SERVICO, "aliquota": "0.02"})
        assert a.hash_laudo != b.hash_laudo

    def test_valor_diferente_muda_o_laudo(self) -> None:
        a = montar()
        b = montar(servico={**SERVICO, "valor": "200.00"})
        assert a.hash_laudo != b.hash_laudo

    def test_trace_diferente_muda_o_laudo(self) -> None:
        a = montar()
        b = montar(trace_id=uuid.UUID("22222222-2222-2222-2222-222222222222"))
        assert a.hash_laudo != b.hash_laudo
