"""Status de CT-e: mensagem montada do XSD e parâmetros do WSDL.

A montagem é validada contra o schema oficial; os parâmetros de SOAP vêm do WSDL e foram
confirmados com chamada real (`cStat 107` no SVRS para ES).
"""

from __future__ import annotations

import pytest
from app.cte.consulta import (
    ACAO,
    ELEMENTO_DADOS,
    NS_SERVICO,
    SOAP_VERSAO,
    montar_cons_stat_serv_cte,
)
from lxml import etree

XS = "{http://www.w3.org/2001/XMLSchema}"
SCHEMA = "tests/fixtures/schemas/cte-4.00/consStatServCTe_v4.00.xsd"


class TestMontagem:
    def test_valida_contra_o_xsd_oficial(self) -> None:
        xml = montar_cons_stat_serv_cte(cuf="32")
        schema = etree.XMLSchema(etree.parse(SCHEMA))
        assert schema.validate(etree.fromstring(xml))

    def test_traz_cuf_que_o_leiaute_exige(self) -> None:
        # O `consStatServ` de NF-e não tem cUF; o de CT-e tem. Confundir dá 243.
        xml = montar_cons_stat_serv_cte(cuf="32")
        assert b"<cUF>32</cUF>" in xml

    def test_ambiente_vai_no_tp_amb(self) -> None:
        assert b"<tpAmb>2</tpAmb>" in montar_cons_stat_serv_cte(cuf="32", ambiente="2")
        assert b"<tpAmb>1</tpAmb>" in montar_cons_stat_serv_cte(cuf="32", ambiente="1")

    def test_cuf_invalido_recusa(self) -> None:
        with pytest.raises(ValueError, match="2 dígitos"):
            montar_cons_stat_serv_cte(cuf="3")

    def test_ambiente_invalido_recusa(self) -> None:
        with pytest.raises(ValueError, match="ambiente"):
            montar_cons_stat_serv_cte(cuf="32", ambiente="3")


class TestParametrosDoServico:
    """Valores do WSDL — trocar qualquer um já produziu erro medido na SEFAZ."""

    def test_soap_e_12(self) -> None:
        # Com 1.1 o SVRS devolve HTTP 500 para CT-e (NF-e é o contrário).
        assert SOAP_VERSAO == "1.2"

    def test_wrapper_e_cte_dados_msg(self) -> None:
        # Com `nfeDadosMsg` a SEFAZ responde 243 "XML Mal Formado".
        assert ELEMENTO_DADOS == "cteDadosMsg"

    def test_acao_e_do_servico_de_status(self) -> None:
        assert f"{NS_SERVICO}/cteStatusServicoCT" == ACAO
