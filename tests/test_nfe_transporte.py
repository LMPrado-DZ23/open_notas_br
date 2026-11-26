"""Cliente SOAP: transporte falso, Fault, timeout e preservação da resposta."""

from __future__ import annotations

import pytest
from app.nfe.transporte import (
    ClienteSefaz,
    ErroSefazDefinitivo,
    ErroTransporte,
)

URL = "https://homologacao.sefaz.example/nfe/status"

RESPOSTA_OK = (
    b'<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
    b'<soap12:Body><retConsStatServ xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
    b"<cStat>107</cStat><xMotivo>Servico em Operacao</xMotivo>"
    b"</retConsStatServ></soap12:Body></soap12:Envelope>"
)

RESPOSTA_FAULT = (
    b'<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
    b"<soap12:Body><soap12:Fault><soap12:Code><soap12:Value>soap:Sender"
    b"</soap12:Value></soap12:Code><soap12:Reason><soap12:Text>schema invalido"
    b"</soap12:Text></soap12:Reason></soap12:Fault></soap12:Body></soap12:Envelope>"
)


class TransporteFalso:
    def __init__(self, resposta: bytes | Exception) -> None:
        self._resposta = resposta
        self.chamadas: list[dict] = []

    async def enviar(self, *, url: str, corpo: bytes, timeout_s: float) -> bytes:
        self.chamadas.append({"url": url, "corpo": corpo, "timeout_s": timeout_s})
        if isinstance(self._resposta, Exception):
            raise self._resposta
        return self._resposta


class TestSucesso:
    async def test_devolve_resposta_desenvelopada(self) -> None:
        transporte = TransporteFalso(RESPOSTA_OK)
        resposta = await ClienteSefaz(transporte).chamar(url=URL, xml_fiscal=b"<consStatServ/>")
        assert resposta.cstat == "107"
        assert resposta.texto("xMotivo") == "Servico em Operacao"

    async def test_preserva_o_xml_bruto_para_auditoria(self) -> None:
        transporte = TransporteFalso(RESPOSTA_OK)
        resposta = await ClienteSefaz(transporte).chamar(url=URL, xml_fiscal=b"<consStatServ/>")
        assert resposta.xml == RESPOSTA_OK

    async def test_envia_envelope_nao_o_xml_cru(self) -> None:
        transporte = TransporteFalso(RESPOSTA_OK)
        await ClienteSefaz(transporte).chamar(url=URL, xml_fiscal=b"<consStatServ/>")
        enviado = transporte.chamadas[0]["corpo"]
        assert b"Envelope" in enviado
        assert b"nfeDadosMsg" in enviado


class TestFalhas:
    async def test_fault_e_definitivo(self) -> None:
        transporte = TransporteFalso(RESPOSTA_FAULT)
        with pytest.raises(ErroSefazDefinitivo, match="schema invalido"):
            await ClienteSefaz(transporte).chamar(url=URL, xml_fiscal=b"<x/>")

    async def test_timeout_e_transitorio(self) -> None:
        transporte = TransporteFalso(TimeoutError("estourou"))
        with pytest.raises(ErroTransporte):
            await ClienteSefaz(transporte).chamar(url=URL, xml_fiscal=b"<x/>")

    async def test_conexao_recusada_e_transitoria(self) -> None:
        transporte = TransporteFalso(ConnectionError("recusada"))
        with pytest.raises(ErroTransporte):
            await ClienteSefaz(transporte).chamar(url=URL, xml_fiscal=b"<x/>")

    async def test_html_de_gateway_e_transitorio(self) -> None:
        # Proxy devolve HTML: o serviço pode voltar, então é transitório.
        transporte = TransporteFalso(b"<html>502</html>")
        with pytest.raises(ErroTransporte, match="inesperada"):
            await ClienteSefaz(transporte).chamar(url=URL, xml_fiscal=b"<x/>")


class TestGuardaDeUrl:
    async def test_http_e_recusado(self) -> None:
        transporte = TransporteFalso(RESPOSTA_OK)
        with pytest.raises(ValueError, match="https"):
            await ClienteSefaz(transporte).chamar(
                url="http://inseguro.example/x", xml_fiscal=b"<x/>"
            )

    async def test_url_recusada_nao_chega_ao_transporte(self) -> None:
        transporte = TransporteFalso(RESPOSTA_OK)
        with pytest.raises(ValueError):
            await ClienteSefaz(transporte).chamar(
                url="http://inseguro.example/x", xml_fiscal=b"<x/>"
            )
        assert transporte.chamadas == []
