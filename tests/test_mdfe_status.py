"""Status de MDF-e: mensagem do XSD e parâmetros do WSDL, fixados por teste."""

from __future__ import annotations

import pytest
from app.mdfe.consulta import (
    ACAO,
    ELEMENTO_DADOS,
    NS_SERVICO,
    SOAP_VERSAO,
    montar_cons_stat_serv_mdfe,
)
from lxml import etree

SCHEMA = "tests/fixtures/schemas/mdfe-3.00/consStatServMDFe_v3.00.xsd"


class TestMontagem:
    def test_valida_contra_o_xsd_oficial(self) -> None:
        xml = montar_cons_stat_serv_mdfe()
        assert etree.XMLSchema(etree.parse(SCHEMA)).validate(etree.fromstring(xml))

    def test_nao_tem_cuf(self) -> None:
        # Diferente do CT-e: o consStatServMDFe não leva cUF. Inventar um daria 215.
        assert b"<cUF>" not in montar_cons_stat_serv_mdfe()

    def test_versao_do_leiaute_e_3_00(self) -> None:
        assert b'versao="3.00"' in montar_cons_stat_serv_mdfe()

    def test_ambiente_vai_no_tp_amb(self) -> None:
        assert b"<tpAmb>2</tpAmb>" in montar_cons_stat_serv_mdfe(ambiente="2")

    def test_ambiente_invalido_recusa(self) -> None:
        with pytest.raises(ValueError, match="ambiente"):
            montar_cons_stat_serv_mdfe(ambiente="9")


class TestParametrosDoServico:
    def test_soap_e_12(self) -> None:
        assert SOAP_VERSAO == "1.2"

    def test_wrapper_e_mdfe_dados_msg(self) -> None:
        assert ELEMENTO_DADOS == "mdfeDadosMsg"

    def test_acao_e_do_servico_de_status(self) -> None:
        assert f"{NS_SERVICO}/mdfeStatusServicoMDF" == ACAO
