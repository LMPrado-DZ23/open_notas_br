"""Testes da chave de acesso de 44 dígitos.

O vetor de DV usado aqui foi conferido por três formulações independentes do
módulo 11 (soma reversa com pesos ciclados, soma por distância até o fim e a
implementação do pacote). Ele é **sintético** — não é chave de documento real.
"""

from __future__ import annotations

import pytest

from notasbr.chave import (
    MODELOS,
    TIPO_POR_MODELO,
    UFS,
    ChaveAcesso,
    calcular_dv,
    chave_valida,
    montar_chave,
)
from notasbr.erros import ChaveInvalida

BASE_43 = "3525011122233300018155001000000123112345678"
DV_CONHECIDO = "2"
CHAVE_SP = BASE_43 + DV_CONHECIDO


class TestDigitoVerificador:
    def test_vetor_conhecido(self) -> None:
        assert calcular_dv(BASE_43) == DV_CONHECIDO

    def test_rejeita_base_com_tamanho_errado(self) -> None:
        with pytest.raises(ValueError, match="43"):
            calcular_dv(BASE_43[:-1])

    def test_dv_nunca_e_dois_digitos(self) -> None:
        # Resto 0 ou 1 resulta em "0"; qualquer outro caso é 11 - resto <= 9.
        for semente in range(200):
            base = str(semente).zfill(43)
            dv = calcular_dv(base)
            assert len(dv) == 1
            assert dv.isdigit()

    def test_chave_valida_aceita_e_rejeita(self) -> None:
        assert chave_valida(CHAVE_SP)
        assert not chave_valida(CHAVE_SP[:-1] + "3")
        assert not chave_valida(CHAVE_SP[:-1])
        assert not chave_valida("")
        assert not chave_valida(None)


class TestMontarChave:
    def test_monta_com_zeros_a_esquerda(self) -> None:
        chave = montar_chave(
            c_uf="35",
            aamm="2501",
            cnpj="11222333000181",
            modelo="55",
            serie=1,
            numero=123,
            tp_emis="1",
            c_nf="12345678",
        )
        assert chave == CHAVE_SP
        assert len(chave) == 44

    def test_aamm_precisa_de_quatro_digitos(self) -> None:
        with pytest.raises(ValueError, match="AAMM"):
            montar_chave(
                c_uf="35",
                aamm="250",
                cnpj="11222333000181",
                modelo="55",
                serie=1,
                numero=123,
                c_nf="12345678",
            )

    def test_campos_grandes_demais_estouram(self) -> None:
        with pytest.raises(ValueError):
            montar_chave(
                c_uf="35",
                aamm="2501",
                cnpj="11222333000181",
                modelo="55",
                serie=1,
                numero=1,
                c_nf="123456789",  # 9 dígitos: não cabe em 8
            )


class TestParsing:
    def test_decompoe_campos(self) -> None:
        chave = ChaveAcesso.parse(CHAVE_SP)
        assert chave.valor == CHAVE_SP
        assert chave.c_uf == "35"
        assert chave.uf == "SP"
        assert chave.aamm == "2501"
        assert (chave.ano, chave.mes) == (2025, 1)
        assert chave.cnpj == "11222333000181"
        assert chave.modelo == "55"
        assert chave.modelo_nome == "NF-e"
        assert chave.tipo == "nfe"
        assert chave.serie == "001"
        assert chave.serie_int == 1
        assert chave.numero == "000000123"
        assert chave.numero_int == 123
        assert chave.tp_emis == "1"
        assert chave.c_nf == "12345678"
        assert chave.dv == DV_CONHECIDO

    def test_formatacao_em_blocos_de_quatro(self) -> None:
        assert ChaveAcesso.parse(CHAVE_SP).formatada() == (
            "3525 0111 2223 3300 0181 5500 1000 0001 2311 2345 6782"
        )

    def test_to_dict_serializavel(self) -> None:
        dados = ChaveAcesso.parse(CHAVE_SP).to_dict()
        assert dados["chave"] == CHAVE_SP
        assert dados["uf"] == "SP"
        assert dados["forma_emissao"] == "Normal"

    @pytest.mark.parametrize(
        "entrada",
        [
            "",
            "123",
            CHAVE_SP[:-1],
            CHAVE_SP[:-1] + "3",
            "3525011122233300018155001000000123112345678X",
        ],
    )
    def test_rejeita_entrada_invalida(self, entrada: str) -> None:
        with pytest.raises(ChaveInvalida):
            ChaveAcesso.parse(entrada)

    def test_ignora_separadores(self) -> None:
        chave = ChaveAcesso.parse("3525 0111 2223 3300 0181 5500 1000 0001 2311 2345 6782")
        assert chave.valor == CHAVE_SP


class TestTabelas:
    def test_ufs_conhecidas(self) -> None:
        assert UFS["35"] == "SP"
        assert UFS["53"] == "DF"
        assert len(UFS) == 27  # 26 estados + DF

    def test_modelos(self) -> None:
        assert MODELOS["55"] == "NF-e"
        assert MODELOS["65"] == "NFC-e"
        assert MODELOS["57"] == "CT-e"
        assert TIPO_POR_MODELO["55"] == "nfe"
        assert TIPO_POR_MODELO["67"] == "cte"
        assert "58" not in TIPO_POR_MODELO  # MDF-e não é auditado nesta versão
