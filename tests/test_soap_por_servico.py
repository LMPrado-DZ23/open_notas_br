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

from app.nfe.soap import NS_NFE, NS_SOAP12, envelopar
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
