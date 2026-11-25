"""Testes de CNPJ/CPF.

Os documentos usados são os exemplos didáticos públicos da documentação contábil
brasileira (11.222.333/0001-81 e 111.444.777-35), não dados de pessoas.
"""

from __future__ import annotations

import pytest

from notasbr.cadastros import (
    apenas_digitos,
    cnpj_valido,
    cpf_valido,
    documento_valido,
    dv_cnpj,
    dv_cpf,
    formatar_cnpj,
    formatar_cpf,
    mascarar,
)


class TestCnpj:
    @pytest.mark.parametrize(
        "valor",
        ["11222333000181", "11.222.333/0001-81", " 11 222 333 0001 81 "],
    )
    def test_aceita_variacoes_de_formatacao(self, valor: str) -> None:
        assert cnpj_valido(valor)

    @pytest.mark.parametrize(
        "valor",
        [
            "11222333000182",  # DV trocado
            "1122233300018",  # 13 dígitos
            "112223330001811",  # 15 dígitos
            "00000000000000",  # repetição
            "abcdefghijklmn",  # não numérico
            "",
        ],
    )
    def test_rejeita(self, valor: str) -> None:
        assert not cnpj_valido(valor)

    def test_dv_calculado(self) -> None:
        assert dv_cnpj("112223330001") == "81"

    def test_dv_exige_doze_digitos(self) -> None:
        with pytest.raises(ValueError, match="12"):
            dv_cnpj("11222333000")

    def test_formatacao(self) -> None:
        assert formatar_cnpj("11222333000181") == "11.222.333/0001-81"
        assert formatar_cnpj("123") == "123"


class TestCpf:
    @pytest.mark.parametrize("valor", ["11144477735", "111.444.777-35"])
    def test_aceita_variacoes_de_formatacao(self, valor: str) -> None:
        assert cpf_valido(valor)

    @pytest.mark.parametrize(
        "valor",
        [
            "11144477736",
            "1114447773",
            "11111111111",
            "111444777353",
            "",
        ],
    )
    def test_rejeita(self, valor: str) -> None:
        assert not cpf_valido(valor)

    def test_dv_calculado(self) -> None:
        assert dv_cpf("111444777") == "35"

    def test_formatacao(self) -> None:
        assert formatar_cpf("11144477735") == "111.444.777-35"


class TestGenericos:
    @pytest.mark.parametrize(
        ("valor", "esperado"),
        [
            ("11222333000181", True),
            ("11144477735", True),
            ("123", False),
            (None, False),
        ],
    )
    def test_documento_valido(self, valor: str | None, esperado: bool) -> None:
        assert documento_valido(valor) is esperado

    def test_apenas_digitos(self) -> None:
        assert apenas_digitos("11.222.333/0001-81") == "11222333000181"
        assert apenas_digitos(None) == ""

    def test_mascarar_preserva_so_o_final(self) -> None:
        assert mascarar("11222333000181") == "************81"
        assert mascarar("12") == "**"
        assert mascarar("") == ""
