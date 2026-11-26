"""Ciclo de autorização: sequência, recibo e não insistir em rejeição."""

from __future__ import annotations

import pytest
from app.nfe.autorizacao import ErroDeAutorizacao, autorizar, consultar_recibo, enviar_lote
from app.nfe.retorno import Situacao
from app.nfe.transporte import ClienteSefaz

URL_ENVIO = "https://homolog.example/nfe/autorizacao"
URL_RECIBO = "https://homolog.example/nfe/retorno"
NS = "http://www.portalfiscal.inf.br/nfe"


def soap(corpo: str) -> bytes:
    return (
        f'<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        f"<soap12:Body>{corpo}</soap12:Body></soap12:Envelope>"
    ).encode()


def retorno(cstat: str, prot: str | None = None, recibo: str | None = None) -> bytes:
    extra = ""
    if recibo:
        extra += f"<nRecibo>{recibo}</nRecibo>"
    if prot:
        extra += (
            f"<protNFe versao='4.00'><infProt><chNFe>{'1' * 44}</chNFe>"
            f"<cStat>{prot}</cStat><xMotivo>m</xMotivo><nProt>135000000000001</nProt>"
            f"</infProt></protNFe>"
        )
    return soap(
        f"<retEnviNFe xmlns='{NS}' versao='4.00'><cStat>{cstat}</cStat>"
        f"<xMotivo>motivo</xMotivo>{extra}</retEnviNFe>"
    )


class TransporteSequencia:
    """Devolve respostas na ordem; falha se pedirem mais do que o previsto."""

    def __init__(self, respostas: list[bytes]) -> None:
        self._respostas = list(respostas)
        self.urls: list[str] = []

    async def enviar(self, *, url: str, corpo: bytes, timeout_s: float) -> bytes:
        self.urls.append(url)
        if not self._respostas:
            raise AssertionError("chamada inesperada ao transporte")
        return self._respostas.pop(0)


class TestSincrono:
    async def test_autorizada_na_primeira_resposta(self) -> None:
        transporte = TransporteSequencia([retorno("104", prot="100")])
        resultado = await enviar_lote(
            ClienteSefaz(transporte), url=URL_ENVIO, xml_lote=b"<enviNFe/>"
        )
        assert resultado.autorizada is True
        assert resultado.precisa_consultar_recibo is False
        assert resultado.protocolo is not None

    async def test_rejeicao_nao_pede_recibo(self) -> None:
        transporte = TransporteSequencia([retorno("104", prot="539")])
        resultado = await enviar_lote(
            ClienteSefaz(transporte), url=URL_ENVIO, xml_lote=b"<enviNFe/>"
        )
        assert resultado.autorizada is False
        assert resultado.situacao is Situacao.REJEITADA
        assert resultado.precisa_consultar_recibo is False


class TestAssincrono:
    async def test_103_devolve_recibo_e_pede_consulta(self) -> None:
        transporte = TransporteSequencia([retorno("103", recibo="521000000000001")])
        resultado = await enviar_lote(
            ClienteSefaz(transporte), url=URL_ENVIO, xml_lote=b"<enviNFe/>"
        )
        assert resultado.situacao is Situacao.LOTE_RECEBIDO
        assert resultado.recibo == "521000000000001"
        assert resultado.precisa_consultar_recibo is True

    async def test_autorizar_consulta_o_recibo(self) -> None:
        transporte = TransporteSequencia([retorno("103", recibo="521"), retorno("104", prot="100")])
        resultado = await autorizar(
            ClienteSefaz(transporte),
            url_envio=URL_ENVIO,
            url_recibo=URL_RECIBO,
            xml_lote=b"<enviNFe/>",
            montar_consulta=lambda r: f"<consReciNFe><nRec>{r}</nRec></consReciNFe>".encode(),
        )
        assert resultado.autorizada is True
        assert transporte.urls == [URL_ENVIO, URL_RECIBO]

    async def test_sincrono_nao_consulta_recibo(self) -> None:
        transporte = TransporteSequencia([retorno("104", prot="100")])
        await autorizar(
            ClienteSefaz(transporte),
            url_envio=URL_ENVIO,
            url_recibo=URL_RECIBO,
            xml_lote=b"<enviNFe/>",
            montar_consulta=lambda r: b"<x/>",
        )
        assert transporte.urls == [URL_ENVIO], "não deve consultar recibo sem 103"

    async def test_recibo_ainda_processando_nao_insiste(self) -> None:
        # Consulta devolve 103 de novo: para, não fica em laço gastando cota.
        transporte = TransporteSequencia([retorno("103", recibo="521"), retorno("103")])
        resultado = await autorizar(
            ClienteSefaz(transporte),
            url_envio=URL_ENVIO,
            url_recibo=URL_RECIBO,
            xml_lote=b"<enviNFe/>",
            montar_consulta=lambda r: b"<x/>",
            tentativas_recibo=1,
        )
        assert resultado.situacao is Situacao.LOTE_RECEBIDO
        assert len(transporte.urls) == 2


class TestFault:
    async def test_fault_vira_erro_de_autorizacao(self) -> None:
        from app.nfe.transporte import TransporteSOAP

        class Fault(TransporteSOAP):  # type: ignore[misc]
            async def enviar(self, *, url: str, corpo: bytes, timeout_s: float) -> bytes:
                return (
                    b'<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
                    b"<soap12:Body><soap12:Fault><soap12:Code><soap12:Value>Sender"
                    b"</soap12:Value></soap12:Code><soap12:Reason><soap12:Text>x"
                    b"</soap12:Text></soap12:Reason></soap12:Fault></soap12:Body>"
                    b"</soap12:Envelope>"
                )

        with pytest.raises(ErroDeAutorizacao, match="recusou"):
            await enviar_lote(ClienteSefaz(Fault()), url=URL_ENVIO, xml_lote=b"<x/>")


class TestConsultaIsolada:
    async def test_consulta_devolve_protocolo(self) -> None:
        transporte = TransporteSequencia([retorno("104", prot="100")])
        resultado = await consultar_recibo(
            ClienteSefaz(transporte), url=URL_RECIBO, xml_consulta=b"<x/>"
        )
        assert resultado.autorizada is True
