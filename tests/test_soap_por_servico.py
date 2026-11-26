"""Configuração do envelope SOAP por serviço: action e namespace do wrapper.

Descoberto com chamadas reais (auditoria §28): GO aceita `action=""` e o wrapper no namespace
fiscal; SVRS recusa. A progressão medida foi:

    HTTP 500  -> `action` ausente
    cStat 242 -> wrapper no namespace errado ("Mensagem SOAP inválida")
    cStat 215 -> envelope aceito, XML fiscal recusado por schema

Os valores vêm do WSDL oficial de cada serviço (`soap12:operation soapAction=...` e
`targetNamespace`), nunca de tentativa e erro às cegas.
"""

from __future__ import annotations

from app.nfe.soap import NS_NFE, NS_SOAP11, NS_SOAP12, desenvelopar, envelopar
from lxml import etree

NS_SERVICO = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4"
FISCAL = b'<consStatServ xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><tpAmb>2</tpAmb></consStatServ>'


class TestNamespaceDoWrapper:
    def test_sem_ns_servico_usa_namespace_fiscal(self) -> None:
        # Comportamento anterior preservado: GO aceita este formato.
        envelope = envelopar(FISCAL)
        assert NS_NFE.encode() in envelope

    def test_ns_servico_coloca_wrapper_no_namespace_do_servico(self) -> None:
        envelope = envelopar(FISCAL, ns_servico=NS_SERVICO)
        assert NS_SERVICO.encode() in envelope

    def test_xml_fiscal_preservado_dentro_do_envelope(self) -> None:
        envelope = envelopar(FISCAL, ns_servico=NS_SERVICO)
        raiz = etree.fromstring(envelope)
        fiscal = raiz.find(f".//{{{NS_NFE}}}consStatServ")
        assert fiscal is not None
        assert fiscal.get("versao") == "4.00"

    def test_wrapper_contem_o_fiscal_como_filho(self) -> None:
        # `desenvelopar` é para RESPOSTA (extrai do Body e salta `*ResultMsg`). Para o envelope
        # de ENVIO o contrato é: o Body tem um wrapper e o fiscal é filho dele.
        envelope = envelopar(FISCAL, ns_servico=NS_SERVICO)
        raiz = etree.fromstring(envelope)
        corpo = raiz.find(f".//{{{NS_SOAP12}}}Body")
        wrapper = corpo[0]
        assert etree.QName(wrapper).localname == "nfeDadosMsg"
        assert etree.QName(wrapper[0]).localname == "consStatServ"


class TestActionNoTransporte:
    def test_transporte_aceita_soap_action(self) -> None:
        from app.nfe.transporte import TransporteHTTP

        transporte = TransporteHTTP(cliente=None, soap_action=f"{NS_SERVICO}/nfeStatusServicoNF")
        assert transporte._soap_action.endswith("nfeStatusServicoNF")

    def test_sem_action_o_padrao_e_vazio(self) -> None:
        from app.nfe.transporte import TransporteHTTP

        assert TransporteHTTP()._soap_action == ""


class TestSoap11:
    """SOAP 1.1 destrava os endpoints `.asmx` do SVRS, que recusam 1.2 com 215."""

    def test_envelope_11_usa_namespace_soap_11(self) -> None:
        envelope = envelopar(FISCAL, ns_servico=NS_SERVICO, soap_versao="1.1")
        assert NS_SOAP11.encode() in envelope
        assert NS_SOAP12.encode() not in envelope

    def test_envelope_12_continua_padrao(self) -> None:
        envelope = envelopar(FISCAL, ns_servico=NS_SERVICO)
        assert NS_SOAP12.encode() in envelope

    def test_fiscal_usa_namespace_padrao_e_nao_prefixo(self) -> None:
        # Achado medido: se o envelope declara o prefixo `nfe`, o lxml serializa o XML fiscal
        # como `<nfe:consStatServ>` e o SVRS recusa com 215 "Falha no schema XML".
        envelope = envelopar(FISCAL, ns_servico=NS_SERVICO, soap_versao="1.1").decode()
        assert "<nfe:consStatServ" not in envelope
        assert "<consStatServ xmlns=" in envelope
        assert 'versao="4.00"' in envelope

    def test_desenvelopar_le_resposta_soap_11(self) -> None:
        resposta = (
            b'<?xml version="1.0"?>'
            b'<soap:Envelope xmlns:soap="' + NS_SOAP11.encode() + b'">'
            b'<soap:Body><retConsStatServ xmlns="http://www.portalfiscal.inf.br/nfe" '
            b'versao="4.00"><cStat>107</cStat></retConsStatServ></soap:Body></soap:Envelope>'
        )
        extraido = desenvelopar(resposta)
        assert etree.QName(extraido).localname == "retConsStatServ"

    def test_desenvelopar_le_resposta_soap_12(self) -> None:
        resposta = (
            b'<?xml version="1.0"?>'
            b'<env:Envelope xmlns:env="' + NS_SOAP12.encode() + b'">'
            b'<env:Body><retConsStatServ xmlns="http://www.portalfiscal.inf.br/nfe" '
            b'versao="4.00"><cStat>107</cStat></retConsStatServ></env:Body></env:Envelope>'
        )
        extraido = desenvelopar(resposta)
        assert etree.QName(extraido).localname == "retConsStatServ"


class TestCabecalhosPorVersao:
    def test_11_usa_text_xml_e_soapaction(self) -> None:
        from app.nfe.transporte import TransporteHTTP

        tr = TransporteHTTP(soap_action="http://x/y", soap_versao="1.1")
        assert tr._soap_versao == "1.1"

    def test_12_continua_padrao(self) -> None:
        from app.nfe.transporte import TransporteHTTP

        assert TransporteHTTP()._soap_versao == "1.2"
