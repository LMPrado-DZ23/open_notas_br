"""Consulta de situação do CT-e: mensagem do XSD e parâmetros do WSDL."""

from __future__ import annotations

import pytest
from app.cte.consulta_situacao import (
    ACAO,
    ELEMENTO_DADOS,
    NS_SERVICO,
    SOAP_VERSAO,
    montar_cons_sit_cte,
)
from lxml import etree

SCHEMA = "tests/fixtures/schemas/cte-4.00/consSitCTe_v4.00.xsd"
CHAVE = "52" + "9" * 42


class TestMontagem:
    def test_valida_contra_o_xsd_oficial(self) -> None:
        xml = montar_cons_sit_cte(chave=CHAVE)
        assert etree.XMLSchema(etree.parse(SCHEMA)).validate(etree.fromstring(xml))

    def test_traz_a_chave_e_xserv(self) -> None:
        xml = montar_cons_sit_cte(chave=CHAVE)
        assert CHAVE.encode() in xml
        assert b"<xServ>CONSULTAR</xServ>" in xml

    def test_nao_tem_cuf(self) -> None:
        # Consulta difere do status: aqui não entra cUF.
        assert b"<cUF>" not in montar_cons_sit_cte(chave=CHAVE)

    def test_chave_curta_recusa(self) -> None:
        with pytest.raises(ValueError, match="44 dígitos"):
            montar_cons_sit_cte(chave="123")

    def test_ambiente_invalido_recusa(self) -> None:
        with pytest.raises(ValueError, match="ambiente"):
            montar_cons_sit_cte(chave=CHAVE, ambiente="9")


class TestParametrosDoServico:
    def test_soap_e_12(self) -> None:
        assert SOAP_VERSAO == "1.2"

    def test_wrapper_e_cte_dados_msg(self) -> None:
        assert ELEMENTO_DADOS == "cteDadosMsg"

    def test_acao_e_da_consulta(self) -> None:
        assert f"{NS_SERVICO}/cteConsultaCT" == ACAO
