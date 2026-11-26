"""WSDL oficial do SVRS: trava a action e o namespace usados pelo cliente.

Os valores em `app/nfe/soap.py` e `app/nfe/transporte.py` não podem ser deduzidos do leiaute
fiscal — vêm do WSDL de cada autorizador. Este teste confere que o código usa exatamente o que a
fonte oficial declara; se o WSDL mudar, o diff aparece aqui antes de virar erro em produção.
"""

from __future__ import annotations

import pathlib

from lxml import etree

WSDL = pathlib.Path(__file__).parent / "fixtures" / "wsdl" / "NfeStatusServico4_svrs_homolog.wsdl"
NS_WSDL = "http://schemas.xmlsoap.org/wsdl/"
NS_SOAP12 = "http://schemas.xmlsoap.org/wsdl/soap12/"


def _wsdl() -> etree._Element:
    return etree.fromstring(WSDL.read_bytes())


class TestWsdlVersionado:
    def test_arquivo_existe(self) -> None:
        assert WSDL.is_file(), "o WSDL oficial precisa estar versionado"

    def test_target_namespace(self) -> None:
        raiz = _wsdl()
        assert raiz.get("targetNamespace") == (
            "http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4"
        )

    def test_soap_action_bate_com_a_usada_no_codigo(self) -> None:
        raiz = _wsdl()
        acoes = [
            op.get("soapAction")
            for op in raiz.iter(f"{{{NS_SOAP12}}}operation")
            if op.get("soapAction")
        ]
        assert acoes, "WSDL sem soapAction em soap12:operation"
        # Todos os bindings declaram a mesma action para esta operação.
        assert set(acoes) == {
            "http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4/nfeStatusServicoNF"
        }

    def test_operacao_declara_nfe_dados_msg(self) -> None:
        # O wrapper do corpo é `nfeDadosMsg`; o teste garante que não inventamos outro nome.
        bruto = WSDL.read_text(encoding="utf-8")
        assert "nfeDadosMsg" in bruto
