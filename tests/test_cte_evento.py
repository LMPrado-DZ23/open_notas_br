"""Evento de CT-e: parâmetros do WSDL e recusas de entrada."""

from __future__ import annotations

import pytest
from app.cte.evento import ACAO, ELEMENTO_DADOS, NS_SERVICO, SOAP_VERSAO, montar_evento

CHAVE = "52" + "9" * 42
CNPJ = "11222333000181"


class TestParametrosDoServico:
    def test_soap_e_12(self) -> None:
        assert SOAP_VERSAO == "1.2"

    def test_wrapper_e_cte_dados_msg(self) -> None:
        assert ELEMENTO_DADOS == "cteDadosMsg"

    def test_acao_e_do_evento(self) -> None:
        assert f"{NS_SERVICO}/cteRecepcaoEvento" == ACAO


class TestMontagem:
    def test_traz_chave_e_tipo_de_evento(self) -> None:
        xml = montar_evento(chave=CHAVE, tipo_evento="110111", cnpj=CNPJ)
        assert CHAVE.encode() in xml
        assert b"<tpEvento>110111</tpEvento>" in xml

    def test_id_do_evento_combina_tipo_chave_e_sequencia(self) -> None:
        xml = montar_evento(chave=CHAVE, tipo_evento="110111", cnpj=CNPJ, n_seq=2)
        assert f"ID110111{CHAVE}02".encode() in xml

    def test_chave_curta_recusa(self) -> None:
        with pytest.raises(ValueError, match="44 dígitos"):
            montar_evento(chave="1", tipo_evento="110111", cnpj=CNPJ)

    def test_tipo_de_evento_invalido_recusa(self) -> None:
        with pytest.raises(ValueError, match="6 dígitos"):
            montar_evento(chave=CHAVE, tipo_evento="1101", cnpj=CNPJ)

    def test_cnpj_do_emitente_vem_do_chamador(self) -> None:
        # Hardcodar CNPJ numa função de biblioteca faria todo evento sair em nome de outra
        # empresa. Este teste existe porque eu cometi exatamente esse erro.
        xml = montar_evento(chave=CHAVE, tipo_evento="110111", cnpj=CNPJ)
        assert CNPJ.encode() in xml
        assert b"99999999000191" not in xml  # CNPJ alheio ao parâmetro não pode entrar

    def test_cnpj_invalido_recusa(self) -> None:
        with pytest.raises(ValueError, match="14 dígitos"):
            montar_evento(chave=CHAVE, tipo_evento="110111", cnpj="123")

    def test_sequencia_zero_recusa(self) -> None:
        with pytest.raises(ValueError, match="sequência"):
            montar_evento(chave=CHAVE, tipo_evento="110111", cnpj=CNPJ, n_seq=0)
