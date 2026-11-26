"""Auditoria de cálculo: determinismo, normalização e vigência de tabela."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.tax.auditoria import (
    LaudoCalculo,
    TabelaConsultada,
    hash_de,
    tabela_vigente,
)


class TestDeterminismo:
    def test_mesma_entrada_mesmo_hash(self) -> None:
        a = {"valor": Decimal("100.00"), "uf": "GO"}
        b = {"valor": Decimal("100.00"), "uf": "GO"}
        assert hash_de(a) == hash_de(b)

    def test_ordem_das_chaves_nao_importa(self) -> None:
        assert hash_de({"a": 1, "b": 2}) == hash_de({"b": 2, "a": 1})

    def test_decimal_com_casas_diferentes_normaliza(self) -> None:
        # 10.0 e 10.00 são o mesmo valor tributário: não podem gerar hash diferente.
        assert hash_de({"v": Decimal("10.0")}) == hash_de({"v": Decimal("10.00")})

    def test_valor_diferente_muda_o_hash(self) -> None:
        assert hash_de({"v": Decimal("10.00")}) != hash_de({"v": Decimal("11.00")})

    def test_string_numerica_nao_equivale_a_decimal(self) -> None:
        # "10.00" e Decimal("10.00") normalizam igual de propósito: a entrada pode
        # vir do JSON ou do domínio e precisa produzir o mesmo laudo.
        assert hash_de({"v": "10.00"}) == hash_de({"v": Decimal("10.00")})

    def test_lista_preserva_ordem(self) -> None:
        assert hash_de({"itens": [1, 2]}) != hash_de({"itens": [2, 1]})

    def test_hash_tem_64_hex(self) -> None:
        assert len(hash_de({})) == 64


class TestLaudo:
    def test_hashes_separados_de_entrada_e_saida(self) -> None:
        laudo = LaudoCalculo(entrada={"base": Decimal("100.00")}, saida={"iss": Decimal("5.00")})
        assert laudo.hash_entrada != laudo.hash_saida

    def test_hash_do_laudo_muda_com_a_regra(self) -> None:
        base = dict(entrada={"base": Decimal("100.00")}, saida={"iss": Decimal("5.00")})
        a = LaudoCalculo(**base, regras=("ISS alíquota 5%",))
        b = LaudoCalculo(**base, regras=("ISS alíquota 2%",))
        assert a.hash_laudo != b.hash_laudo

    def test_hash_do_laudo_muda_com_a_versao_da_tabela(self) -> None:
        base = dict(entrada={"base": Decimal("100.00")}, saida={"iss": Decimal("5.00")})
        a = LaudoCalculo(**base, tabelas=(TabelaConsultada("iss", "2026.1"),))
        b = LaudoCalculo(**base, tabelas=(TabelaConsultada("iss", "2026.2"),))
        assert a.hash_laudo != b.hash_laudo

    def test_mesmos_dados_mesmo_laudo(self) -> None:
        kwargs = dict(
            entrada={"base": Decimal("100.00")},
            saida={"iss": Decimal("5.00")},
            regras=("regra",),
            data_emissao=date(2026, 11, 25),
            trace_id="abc",
        )
        assert LaudoCalculo(**kwargs).hash_laudo == LaudoCalculo(**kwargs).hash_laudo

    def test_serializacao_traz_valores_e_hashes(self) -> None:
        laudo = LaudoCalculo(
            entrada={"base": Decimal("100.00")},
            saida={"iss": Decimal("5.00")},
            trace_id="t1",
        )
        corpo = laudo.para_dict()
        assert corpo["hash_entrada"] and corpo["hash_saida"] and corpo["hash_laudo"]
        assert corpo["entrada"]["base"] == "100.00"
        assert corpo["versao_formato"] == 1

    def test_sem_trace_id_nao_inventa(self) -> None:
        assert LaudoCalculo(entrada={}, saida={}).para_dict()["trace_id"] is None


class TestVigencia:
    def test_escolhe_a_vigente(self) -> None:
        tabelas = [
            TabelaConsultada("iss", "2025", date(2025, 1, 1), date(2025, 12, 31)),
            TabelaConsultada("iss", "2026", date(2026, 1, 1), None),
        ]
        assert tabela_vigente(tabelas, date(2026, 11, 25)).versao == "2026"

    def test_data_anterior_a_todas_nao_escolhe(self) -> None:
        tabelas = [TabelaConsultada("iss", "2026", date(2026, 1, 1), None)]
        assert tabela_vigente(tabelas, date(2025, 6, 1)) is None

    def test_sobreposicao_de_vigencia_levanta(self) -> None:
        # Sobreposição é defeito de cadastro; escolher uma em silêncio calcularia com
        # a tabela errada.
        tabelas = [
            TabelaConsultada("iss", "A", date(2026, 1, 1), None),
            TabelaConsultada("iss", "B", date(2026, 6, 1), None),
        ]
        with pytest.raises(ValueError, match="mais de uma versão vigente"):
            tabela_vigente(tabelas, date(2026, 11, 25))

    def test_sem_tabela_nenhuma(self) -> None:
        assert tabela_vigente([], date(2026, 1, 1)) is None

    def test_vigencia_aberta_dos_dois_lados(self) -> None:
        assert tabela_vigente([TabelaConsultada("x", "1")], date(2026, 5, 5)) is not None
