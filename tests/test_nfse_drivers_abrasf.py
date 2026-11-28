"""Driver ABRASF: envelope, encoding, assinatura seletiva e leitura de retorno."""

from __future__ import annotations

import pytest
from app.nfse.drivers import CategoriaErro
from app.nfse.drivers_abrasf import (
    AbrasfBaseDriver,
    ConfiguracaoAbrasf,
    ErroAbrasf,
    desenvelopar,
    envelopar,
    interpretar,
)
from lxml import etree

URL = "https://provedor.example/nfse"
NS = "http://www.abrasf.org.br/nfse.xsd"
NS_SOAP12 = "http://www.w3.org/2003/05/soap-envelope"
NS_SOAP11 = "http://schemas.xmlsoap.org/soap/envelope/"

RPS = f'<EnviarLoteRpsEnvio xmlns="{NS}"><LoteRps/></EnviarLoteRpsEnvio>'.encode()


def resposta(corpo: str, *, soap: str = NS_SOAP12) -> bytes:
    return (
        f'<soap:Envelope xmlns:soap="{soap}"><soap:Body>{corpo}</soap:Body></soap:Envelope>'
    ).encode()


SUCESSO = resposta(
    f'<EnviarLoteRpsResposta xmlns="{NS}"><NumeroLote>1</NumeroLote>'
    f"<Protocolo>PROT-123</Protocolo></EnviarLoteRpsResposta>"
)
ERRO = resposta(
    f'<EnviarLoteRpsResposta xmlns="{NS}"><ListaMensagemRetorno><MensagemRetorno>'
    f"<Codigo>E10</Codigo><Mensagem>assinatura invalida</Mensagem>"
    f"</MensagemRetorno></ListaMensagemRetorno></EnviarLoteRpsResposta>"
)


class TransporteFalso:
    def __init__(self, resposta_bytes: bytes) -> None:
        self._resposta = resposta_bytes
        self.chamadas: list[dict] = []

    async def enviar(self, *, url: str, corpo: bytes, encoding: str) -> bytes:
        self.chamadas.append({"url": url, "corpo": corpo, "encoding": encoding})
        return self._resposta


def driver(transporte, **extra) -> AbrasfBaseDriver:
    conf = ConfiguracaoAbrasf(url=URL, namespace=NS, **extra)
    return AbrasfBaseDriver(configuracao=conf, transporte=transporte)


class TestEnvelope:
    def test_soap12_usa_o_namespace_certo(self) -> None:
        env = envelopar(RPS, namespace=NS, versao_soap="1.2")
        raiz = etree.fromstring(env)
        assert etree.QName(raiz).namespace == NS_SOAP12

    def test_soap11_usa_o_namespace_certo(self) -> None:
        env = envelopar(RPS, namespace=NS, versao_soap="1.1")
        raiz = etree.fromstring(env)
        assert etree.QName(raiz).namespace == NS_SOAP11

    def test_declaracao_usa_o_encoding_do_provedor(self) -> None:
        # GINFES/DSF declaram ISO-8859-1; declarar UTF-8 corrompe acentuação.
        env = envelopar(RPS, namespace=NS, encoding="ISO-8859-1")
        # Aspas simples ou duplas são ambas válidas em XML; o que importa é o encoding declarado
        # e existir UMA declaração — duas tornam o documento malformado (defeito corrigido na §130).
        assert b"ISO-8859-1" in env
        assert env.count(b"<?xml") == 1

    def test_xml_fiscal_entra_intacto_no_body(self) -> None:
        env = envelopar(RPS, namespace=NS)
        raiz = etree.fromstring(env)
        corpo = raiz.find(f".//{{{NS_SOAP12}}}Body")
        assert etree.QName(corpo[0]).localname == "EnviarLoteRpsEnvio"

    def test_xml_invalido_levanta(self) -> None:
        with pytest.raises(ErroAbrasf, match="inválido"):
            envelopar(b"<nao-fechado>", namespace=NS)

    def test_versao_desconhecida_levanta(self) -> None:
        with pytest.raises(ErroAbrasf, match="SOAP"):
            envelopar(RPS, namespace=NS, versao_soap="9.9")


class TestDesenvelopar:
    def test_extrai_o_corpo(self) -> None:
        raiz = desenvelopar(SUCESSO)
        assert etree.QName(raiz).localname == "EnviarLoteRpsResposta"

    def test_sem_body_levanta(self) -> None:
        with pytest.raises(ErroAbrasf):
            desenvelopar(b"<Envelope/>")


class TestInterpretar:
    def test_sucesso_extrai_protocolo(self) -> None:
        resultado = interpretar(SUCESSO)
        assert resultado.sucesso is True
        assert resultado.protocolo == "PROT-123"

    def test_lista_de_mensagem_marca_falha(self) -> None:
        resultado = interpretar(ERRO)
        assert resultado.sucesso is False
        assert resultado.codigo == "E10"
        assert resultado.erro_categoria is CategoriaErro.MUNICIPIO

    def test_resposta_nao_xml_nao_explode(self) -> None:
        resultado = interpretar(b"<html>502</html>")
        assert resultado.sucesso is False
        assert resultado.erro_categoria is CategoriaErro.MUNICIPIO


class TestDriver:
    async def test_emitir_envia_para_a_url_do_cadastro(self) -> None:
        transporte = TransporteFalso(SUCESSO)

        async def assinar(xml: bytes) -> bytes:
            return xml

        d = AbrasfBaseDriver(
            configuracao=ConfiguracaoAbrasf(url=URL, namespace=NS, assina_lote=True),
            transporte=transporte,
            assinador=assinar,
        )
        resultado = await d.emitir_rps(dados={"xml": RPS})
        assert resultado.sucesso is True
        assert transporte.chamadas[0]["url"] == URL

    async def test_encoding_configurado_chega_ao_transporte(self) -> None:
        transporte = TransporteFalso(SUCESSO)

        async def assinar(xml: bytes) -> bytes:
            return xml

        d = AbrasfBaseDriver(
            configuracao=ConfiguracaoAbrasf(
                url=URL, namespace=NS, encoding="ISO-8859-1", assina_lote=True
            ),
            transporte=transporte,
            assinador=assinar,
        )
        await d.emitir_rps(dados={"xml": RPS})
        assert transporte.chamadas[0]["encoding"] == "ISO-8859-1"

    async def test_sem_xml_da_validacao(self) -> None:
        resultado = await driver(TransporteFalso(SUCESSO)).emitir_rps(dados={})
        assert resultado.sucesso is False
        assert resultado.erro_categoria is CategoriaErro.VALIDACAO

    async def test_assinador_ausente_nao_finge_sucesso(self) -> None:
        # Provedor exige assinatura: sem assinador, falha claro em vez de enviar sem assinar.
        d = driver(TransporteFalso(SUCESSO), assina_lote=True)
        resultado = await d.emitir_rps(dados={"xml": RPS})
        assert resultado.sucesso is False
        assert resultado.erro_categoria is CategoriaErro.INTERNO

    async def test_assinador_e_usado_quando_injetado(self) -> None:
        transporte = TransporteFalso(SUCESSO)

        async def assinar(xml: bytes) -> bytes:
            return xml.replace(b"<LoteRps/>", b"<LoteRps assinado='1'/>")

        d = AbrasfBaseDriver(
            configuracao=ConfiguracaoAbrasf(url=URL, namespace=NS, assina_lote=True),
            transporte=transporte,
            assinador=assinar,
        )
        await d.emitir_rps(dados={"xml": RPS})
        # lxml reescreve aspas simples como duplas ao serializar o envelope.
        assert b"assinado" in transporte.chamadas[0]["corpo"]

    async def test_consultar_nao_exige_assinatura(self) -> None:
        transporte = TransporteFalso(SUCESSO)
        d = driver(transporte, assina_lote=True)  # sem assinador, e não deve precisar
        resultado = await d.consultar_lote(protocolo="PROT-1")
        assert resultado.sucesso is True

    async def test_operacoes_sem_leiaute_recusam_com_motivo(self) -> None:
        d = driver(TransporteFalso(SUCESSO))
        tomadas = await d.consultar_nfse_tomadas(cnpj_tomador="11222333000181")
        por_rps = await d.consultar_nfse_por_rps(numero_rps="1")
        assert tomadas.sucesso is False and "leiaute" in tomadas.mensagem
        assert por_rps.sucesso is False and "documentação" in por_rps.mensagem

    async def test_url_http_recusada_na_construcao(self) -> None:
        with pytest.raises(ValueError, match="https"):
            AbrasfBaseDriver(
                configuracao=ConfiguracaoAbrasf(url="http://inseguro", namespace=NS),
                transporte=TransporteFalso(SUCESSO),
            )
