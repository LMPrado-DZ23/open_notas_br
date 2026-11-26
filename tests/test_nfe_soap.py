"""Envelope SOAP 1.2: montagem, extração e leitura de Fault."""

from __future__ import annotations

import pytest
from app.nfe.base import Destinatario, Emitente, Item, NotaFiscal
from app.nfe.gerador import gerar_nfe
from app.nfe.soap import NS_SOAP12, ErroSOAP, desenvelopar, envelopar, extrair_falha
from lxml import etree

NS_NFE = "http://www.portalfiscal.inf.br/nfe"


def nota_xml() -> bytes:
    from datetime import datetime
    from decimal import Decimal

    return gerar_nfe(
        NotaFiscal(
            numero=1,
            serie=1,
            emitente=Emitente(
                cnpj="11222333000181",
                nome="E",
                ie="1",
                crt="1",
                logradouro="R",
                numero="1",
                bairro="B",
                municipio="M",
                codigo_municipio="5200258",
                uf="GO",
                cep="72910000",
            ),
            destinatario=Destinatario(
                documento="11144477735",
                nome="D",
                logradouro="R",
                numero="2",
                bairro="B",
                municipio="M",
                codigo_municipio="5208707",
                uf="GO",
                cep="74000000",
            ),
            itens=[
                Item(
                    codigo="1",
                    descricao="P",
                    ncm="12345678",
                    cfop="5102",
                    unidade="UN",
                    quantidade=Decimal("1"),
                    valor_unitario=Decimal("10.00"),
                    valor_total=Decimal("10.00"),
                    cst="00",
                    icms_situacao="102",
                )
            ],
            dh_emissao=datetime(2026, 11, 25, 12, 0),
        )
    )


class TestEnvelopar:
    def test_tem_envelope_e_body(self) -> None:
        envelope = envelopar(nota_xml())
        raiz = etree.fromstring(envelope)
        assert etree.QName(raiz).namespace == NS_SOAP12
        assert raiz.find(f".//{{{NS_SOAP12}}}Body") is not None

    def test_xml_fiscal_vai_dentro_de_nfe_dados_msg(self) -> None:
        raiz = etree.fromstring(envelopar(nota_xml()))
        dados = raiz.find(f".//{{{NS_NFE}}}nfeDadosMsg")
        assert dados is not None
        assert etree.QName(dados[0]).localname == "NFe"

    def test_declaracao_em_utf8(self) -> None:
        assert envelopar(nota_xml()).startswith(b'<?xml version="1.0" encoding="UTF-8"?>')

    def test_xml_invalido_levanta(self) -> None:
        with pytest.raises(ErroSOAP, match="inválido"):
            envelopar(b"<nao-fechado>")


class TestDesenvelopar:
    def test_extrai_o_corpo(self) -> None:
        resposta = (
            b'<?xml version="1.0"?><soap12:Envelope '
            b'xmlns:soap12="http://www.w3.org/2003/05/soap-envelope"><soap12:Body>'
            b'<retConsStatServ xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
            b"<cStat>107</cStat></retConsStatServ></soap12:Body></soap12:Envelope>"
        )
        corpo = desenvelopar(resposta)
        assert etree.QName(corpo).localname == "retConsStatServ"

    def test_sem_body_levanta(self) -> None:
        with pytest.raises(ErroSOAP, match="sem Body"):
            desenvelopar(b'<Envelope xmlns="http://www.w3.org/2003/05/soap-envelope"/>')

    def test_body_vazio_levanta(self) -> None:
        resposta = (
            b'<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
            b"<soap12:Body/></soap12:Envelope>"
        )
        with pytest.raises(ErroSOAP):
            desenvelopar(resposta)

    def test_html_de_gateway_levanta(self) -> None:
        # Proxy no caminho devolve HTML, não SOAP: precisa falhar com mensagem clara.
        with pytest.raises(ErroSOAP):
            desenvelopar(b"<html><body>502 Bad Gateway</body></html>")


class TestFault:
    def test_le_fault(self) -> None:
        resposta = (
            b'<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
            b"<soap12:Body><soap12:Fault><soap12:Code><soap12:Value>soap:Sender"
            b"</soap12:Value></soap12:Code><soap12:Reason><soap12:Text>erro de schema"
            b"</soap12:Text></soap12:Reason></soap12:Fault></soap12:Body></soap12:Envelope>"
        )
        falha = extrair_falha(resposta)
        assert falha is not None
        assert "Sender" in falha["code"]
        assert "schema" in falha["reason"]

    def test_resposta_normal_nao_e_fault(self) -> None:
        # None significa "não é Fault", NÃO "deu certo".
        resposta = (
            b'<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
            b"<soap12:Body><retConsStatServ/></soap12:Body></soap12:Envelope>"
        )
        assert extrair_falha(resposta) is None

    def test_nao_xml_nao_e_fault(self) -> None:
        assert extrair_falha(b"lixo") is None
