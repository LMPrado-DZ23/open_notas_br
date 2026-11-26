"""Integração driver x assinatura: a costura entre os dois módulos."""

from __future__ import annotations

import pytest
from app.certificates.cofre import CertificadoA1
from app.nfse.drivers_abrasf import (
    AbrasfBaseDriver,
    ConfiguracaoAbrasf,
    assinador_de,
    interpretar,
)
from lxml import etree

URL = "https://provedor.example/nfse"
NS = "http://www.abrasf.org.br/nfse.xsd"
NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"

RPS = (
    f'<EnviarLoteRpsEnvio xmlns="{NS}"><LoteRps Id="lote1"><ListaRps><Rps>'
    f'<InfDeclaracaoPrestacaoServico Id="rps1"><Competencia>2026-11-01</Competencia>'
    f"</InfDeclaracaoPrestacaoServico></Rps></ListaRps></LoteRps></EnviarLoteRpsEnvio>"
).encode()

RESPOSTA = (
    f'<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"><soap:Body>'
    f'<EnviarLoteRpsResposta xmlns="{NS}"><Protocolo>P1</Protocolo>'
    f"</EnviarLoteRpsResposta></soap:Body></soap:Envelope>"
).encode()


@pytest.fixture(scope="module")
def certificado() -> CertificadoA1:
    from tests.test_fase2_certificado import SENHA, gerar_pfx

    return CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())


class TransporteCaptura:
    def __init__(self) -> None:
        self.corpos: list[bytes] = []

    async def enviar(self, *, url: str, corpo: bytes, encoding: str) -> bytes:
        self.corpos.append(corpo)
        return RESPOSTA


class TestCostura:
    async def test_driver_assina_com_o_assinador_real(self, certificado) -> None:
        transporte = TransporteCaptura()
        driver = AbrasfBaseDriver(
            configuracao=ConfiguracaoAbrasf(url=URL, namespace=NS, assina_lote=True),
            transporte=transporte,
            assinador=assinador_de(certificado, alvo="rps"),
        )

        resultado = await driver.emitir_rps(dados={"xml": RPS})

        assert resultado.sucesso is True
        enviado = transporte.corpos[0]
        assert b"Signature" in enviado, "o envelope enviado precisa conter a assinatura"
        raiz = etree.fromstring(enviado)
        ref = raiz.find(f".//{{{NS_DSIG}}}Reference")
        assert ref is not None and ref.get("URI") == "#rps1"

    async def test_alvo_lote_usa_o_id_do_lote(self, certificado) -> None:
        transporte = TransporteCaptura()
        driver = AbrasfBaseDriver(
            configuracao=ConfiguracaoAbrasf(url=URL, namespace=NS, assina_lote=True),
            transporte=transporte,
            assinador=assinador_de(certificado, alvo="lote"),
        )
        await driver.emitir_rps(dados={"xml": RPS})
        raiz = etree.fromstring(transporte.corpos[0])
        assert raiz.find(f".//{{{NS_DSIG}}}Reference").get("URI") == "#lote1"

    def test_alvo_invalido_levanta_na_criacao(self, certificado) -> None:
        with pytest.raises(ValueError):
            assinador_de(certificado, alvo="inexistente")


class TestInterpretarRespostaDoDriver:
    def test_resposta_de_sucesso_do_envelope(self) -> None:
        resultado = interpretar(RESPOSTA)
        assert resultado.sucesso is True
        assert resultado.protocolo == "P1"
