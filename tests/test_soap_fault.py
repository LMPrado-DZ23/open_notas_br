"""Fault SOAP em 1.1 e 1.2 — SVRS/SP respondem `.asmx` (1.1) e o erro precisa ser classificado.

Procurar `Fault` apenas no namespace 1.2 fazia o erro de infraestrutura de SVRS/SEFAZ-SP passar como
resposta normal: virava `ErroDeRetorno("elemento não é retorno da SEFAZ: Fault")`, que não é
`ErroSefazDefinitivo` — e um erro definitivo retentado em laço só gasta cota e atrasa o cliente.
"""

from __future__ import annotations

import pytest
from app.nfe.soap import extrair_falha

NS11 = "http://schemas.xmlsoap.org/soap/envelope/"
NS12 = "http://www.w3.org/2003/05/soap-envelope"


def _envelope11(codigo: str = "soap:Server", texto: str = "Erro interno") -> bytes:
    return (
        f'<soap:Envelope xmlns:soap="{NS11}"><soap:Body><soap:Fault>'
        f"<faultcode>{codigo}</faultcode><faultstring>{texto}</faultstring>"
        "</soap:Fault></soap:Body></soap:Envelope>"
    ).encode()


def _envelope12(codigo: str = "env:Receiver", texto: str = "Falha") -> bytes:
    return (
        f'<env:Envelope xmlns:env="{NS12}"><env:Body><env:Fault>'
        f"<env:Code><env:Value>{codigo}</env:Value></env:Code>"
        f'<env:Reason><env:Text xml:lang="pt">{texto}</env:Text></env:Reason>'
        "</env:Fault></env:Body></env:Envelope>"
    ).encode()


class TestFaultSoap11:
    def test_fault_1_1_e_reconhecido(self) -> None:
        falha = extrair_falha(_envelope11())

        assert falha is not None, "Fault de SOAP 1.1 não pode passar como resposta normal"
        assert falha["code"] == "soap:Server"
        assert falha["reason"] == "Erro interno"

    def test_fault_sem_namespace_tambem(self) -> None:
        xml = b"<Envelope><Body><Fault><faultcode>Server</faultcode></Fault></Body></Envelope>"

        falha = extrair_falha(xml)

        assert falha is not None and falha["code"] == "Server"


class TestFaultSoap12:
    def test_fault_1_2_continua_reconhecido(self) -> None:
        falha = extrair_falha(_envelope12())

        assert falha is not None
        assert falha["code"] == "env:Receiver"
        assert falha["reason"] == "Falha"


class TestSemFault:
    @pytest.mark.parametrize(
        "xml",
        [
            b"<Envelope><Body><retEnviNFe><cStat>100</cStat></retEnviNFe></Body></Envelope>",
            b"<nao-fechado>",
        ],
    )
    def test_ausencia_de_fault_devolve_none(self, xml: bytes) -> None:
        assert extrair_falha(xml) is None


class TestIntegracaoComCliente:
    async def test_fault_1_1_vira_erro_definitivo(self) -> None:
        """O caminho que importa: Fault 1.1 não pode virar resposta nem erro transitório."""
        from app.nfe.transporte import ClienteSefaz, ErroSefazDefinitivo

        class TransporteQueDevolveFault:
            async def enviar(self, **kwargs) -> bytes:
                return _envelope11()

        cliente = ClienteSefaz(TransporteQueDevolveFault(), timeout_s=1.0)

        with pytest.raises(ErroSefazDefinitivo) as erro:
            await cliente.chamar(url="https://sefaz.example/ws", xml_fiscal=b"<x/>")

        assert "soap:Server" in str(erro.value)
