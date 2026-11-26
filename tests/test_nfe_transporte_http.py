"""Transporte HTTP: contrato do pedido e tradução de status."""

from __future__ import annotations

import httpx
import pytest
from app.nfe.transporte import ClienteSefaz, ErroTransporte, TransporteHTTP

URL = "https://homologacao.sefaz.example/nfe/status"

RESPOSTA_OK = (
    b'<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
    b'<soap12:Body><retConsStatServ xmlns="http://www.portalfiscal.inf.br/nfe">'
    b"<cStat>107</cStat></retConsStatServ></soap12:Body></soap12:Envelope>"
)


def transporte_contra(handler) -> TransporteHTTP:
    """Transporte real, com `httpx` falando com um handler ASGI local (sem rede)."""
    return TransporteHTTP(cliente=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


class TestContratoDoPedido:
    async def test_envia_como_soap_xml_e_nao_text_xml(self) -> None:
        # SOAP 1.2 usa application/soap+xml; text/xml é SOAP 1.1.
        visto: dict[str, str] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            visto["content_type"] = request.headers.get("content-type", "")
            visto["accept"] = request.headers.get("accept", "")
            return httpx.Response(200, content=RESPOSTA_OK)

        await transporte_contra(handler).enviar(url=URL, corpo=b"<x/>", timeout_s=10)
        assert visto["content_type"].startswith("application/soap+xml")
        assert visto["accept"] == "application/soap+xml"

    async def test_corpo_chega_intacto(self) -> None:
        recebido: list[bytes] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            recebido.append(request.content)
            return httpx.Response(200, content=RESPOSTA_OK)

        corpo = b"<soap12:Envelope/>"
        await transporte_contra(handler).enviar(url=URL, corpo=corpo, timeout_s=10)
        assert recebido == [corpo]

    async def test_devolve_o_conteudo_bruto(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=RESPOSTA_OK)

        saida = await transporte_contra(handler).enviar(url=URL, corpo=b"<x/>", timeout_s=10)
        assert saida == RESPOSTA_OK


class TestStatus:
    async def test_500_e_transitorio(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, content=b"indisponivel")

        with pytest.raises(ErroTransporte, match="503"):
            await transporte_contra(handler).enviar(url=URL, corpo=b"<x/>", timeout_s=10)

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    async def test_5xx_sempre_transitorio(self, status: int) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, content=b"erro")

        with pytest.raises(ErroTransporte):
            await transporte_contra(handler).enviar(url=URL, corpo=b"<x/>", timeout_s=10)


class TestIntegracaoComCliente:
    async def test_cliente_usa_o_transporte_http(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=RESPOSTA_OK)

        cliente = ClienteSefaz(transporte_contra(handler))
        resposta = await cliente.chamar(url=URL, xml_fiscal=b"<consStatServ/>")
        assert resposta.cstat == "107"
