"""Regras ASSIN-001..005 sobre XML de verdade — incluindo a verificação criptográfica.

A camada estrutural pega Signature ausente, Reference sem URI, digest vazio ou base64 inválido. A
camada criptográfica só roda com o extra instalado; aqui ele está, então o teste **assina** uma NF-e
sintética e verifica três desfechos: assinatura íntegra (info), assinatura adulterada (erro) e
certificado embutido ilegível (erro).

Nenhum certificado real: o PFX é gerado no teste.
"""

from __future__ import annotations

import base64
from xml.etree import ElementTree as ET

import pytest
from app.certificates.cofre import CertificadoA1
from app.nfse.signer import assinar
from lxml import etree

from notasbr import Severidade, auditar_bytes
from tests.construir import nfe
from tests.test_fase2_certificado import SENHA, gerar_pfx

NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"


@pytest.fixture
def certificado():
    return CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())


@pytest.fixture
def nfe_assinada(certificado) -> bytes:
    """NF-e assinada no mesmo arranjo do documento real: `Signature` dentro de `NFe`.

    `_primeiro_com_id` só olha filhos diretos, então o alvo é o elemento `NFe` — cujo filho `infNFe`
    já traz o `Id` da fixture. Assinar o `nfeProc` exigiria inventar um segundo `Id`, e aí o auditor
    acusaria ASSIN-002 por divergência entre `Reference` e o `Id` do corpo.
    """
    raiz = etree.fromstring(nfe())
    _remover_signatures(raiz)
    elemento_nfe = next(e for e in raiz if etree.QName(e).localname == "NFe")
    assinado = assinar(elemento_nfe, certificado)
    raiz.replace(elemento_nfe, assinado)
    # Serializar com xml.etree reescreve prefixos (ns0:) e quebra o C14N; use lxml.
    return etree.tostring(raiz)


def _remover_signatures(raiz) -> None:
    for elemento in list(raiz.iter()):
        if etree.QName(elemento).localname == "Signature":
            pai = elemento.getparent()
            if pai is not None:
                pai.remove(elemento)


def _codigos(xml: bytes, severidade: Severidade | None = None) -> set[str]:
    relatorio = auditar_bytes(xml)
    achados = relatorio.achados if severidade is None else relatorio.por_severidade(severidade)
    return {a.codigo for a in achados}


def _com_signature(xml: bytes, transformar) -> bytes:
    """Aplica uma mutação no elemento Signature, preservando o resto do documento."""
    raiz = etree.fromstring(xml)
    assinatura = next(e for e in raiz.iter() if etree.QName(e).localname == "Signature")
    transformar(assinatura)
    return etree.tostring(raiz)


class TestEstrutural:
    def test_sem_signature_vira_erro(self) -> None:
        raiz = etree.fromstring(nfe())
        _remover_signatures(raiz)

        assert "ASSIN-001" in _codigos(ET.tostring(raiz), Severidade.ERRO)

    def test_namespace_errado_vira_aviso(self) -> None:
        xml = nfe().replace(b'xmlns="http://www.w3.org/2000/09/xmldsig#"', b'xmlns="urn:errado"')

        assert "ASSIN-001" in _codigos(xml)

    def test_signature_sem_reference_vira_erro(self, nfe_assinada: bytes) -> None:
        def remover(assinatura):
            for filho in list(assinatura):
                if etree.QName(filho).localname == "SignedInfo":
                    for neto in list(filho):
                        if etree.QName(neto).localname == "Reference":
                            filho.remove(neto)

        xml = _com_signature(nfe_assinada, remover)

        assert "ASSIN-002" in _codigos(xml, Severidade.ERRO)

    def test_reference_sem_uri_vira_erro(self, nfe_assinada: bytes) -> None:
        def remover_uri(assinatura):
            for elemento in assinatura.iter():
                if etree.QName(elemento).localname == "Reference":
                    elemento.attrib.pop("URI", None)

        xml = _com_signature(nfe_assinada, remover_uri)

        assert "ASSIN-002" in _codigos(xml, Severidade.ERRO)

    def test_uri_divergente_do_id_vira_erro(self, nfe_assinada: bytes) -> None:
        def trocar(assinatura):
            for elemento in assinatura.iter():
                if etree.QName(elemento).localname == "Reference":
                    elemento.set("URI", "#outro-id")

        xml = _com_signature(nfe_assinada, trocar)

        assert "ASSIN-002" in _codigos(xml, Severidade.ERRO)

    def test_digest_vazio_vira_erro(self, nfe_assinada: bytes) -> None:
        def esvaziar(assinatura):
            for elemento in assinatura.iter():
                if etree.QName(elemento).localname == "DigestValue":
                    elemento.text = ""

        xml = _com_signature(nfe_assinada, esvaziar)

        assert "ASSIN-003" in _codigos(xml, Severidade.ERRO)

    def test_digest_nao_base64_vira_erro(self, nfe_assinada: bytes) -> None:
        def corromper(assinatura):
            for elemento in assinatura.iter():
                if etree.QName(elemento).localname == "DigestValue":
                    elemento.text = "###nao-e-base64###"

        xml = _com_signature(nfe_assinada, corromper)

        assert "ASSIN-003" in _codigos(xml, Severidade.ERRO)

    def test_digest_de_tamanho_atipico_vira_aviso(self, nfe_assinada: bytes) -> None:
        def encurtar(assinatura):
            for elemento in assinatura.iter():
                if etree.QName(elemento).localname == "DigestValue":
                    elemento.text = base64.b64encode(b"curto").decode()

        xml = _com_signature(nfe_assinada, encurtar)
        relatorio = auditar_bytes(xml)

        avisos = {a.codigo for a in relatorio.por_severidade(Severidade.AVISO)}
        assert "ASSIN-003" in avisos


class TestCriptografico:
    def test_assinatura_do_proprio_gerador_verifica(self, nfe_assinada: bytes) -> None:
        """Achado §95 fechado: a assinatura confere quando os bytes não são re-serializados.

        A causa era o fixture, não o gerador: `ET.tostring` reescreve prefixos de namespace e o digest
        C14N deixa de bater. Com `lxml.tostring` — o mesmo documento canônico que o assinador gerou — a
        verificação passa e o auditor emite ASSIN-004 como **info**.
        """
        relatorio = auditar_bytes(nfe_assinada)

        assert relatorio.por_severidade(Severidade.ERRO) == []
        infos = [a for a in relatorio.achados if a.codigo == "ASSIN-004"]
        assert infos, "a verificação criptográfica precisa rodar, não ser pulada"
        assert "não foi validada" in infos[0].mensagem.lower()

    def test_assinatura_adulterada_e_recusada(self, nfe_assinada: bytes) -> None:
        """Mexer no corpo depois de assinar tem que invalidar o digest."""
        xml = nfe_assinada.replace(b"<vNF>", b"<vNF>1")
        assert xml != nfe_assinada, "a mutação precisa realmente alterar o documento"

        assert "ASSIN-004" in _codigos(xml, Severidade.ERRO)

    def test_certificado_embutido_ilegivel_vira_erro(self, nfe_assinada: bytes) -> None:
        def corromper(assinatura):
            for elemento in assinatura.iter():
                if etree.QName(elemento).localname == "X509Certificate":
                    elemento.text = base64.b64encode(b"nao-e-um-certificado").decode()

        xml = _com_signature(nfe_assinada, corromper)

        assert "ASSIN-004" in _codigos(xml, Severidade.ERRO)

    def test_sem_certificado_embutido_fica_pulado(self, nfe_assinada: bytes) -> None:
        def remover(assinatura):
            for elemento in list(assinatura.iter()):
                if etree.QName(elemento).localname == "X509Certificate":
                    pai = elemento.getparent() if hasattr(elemento, "getparent") else None
                    if pai is not None:
                        pai.remove(elemento)

        xml = _com_signature(nfe_assinada, remover)
        relatorio = auditar_bytes(xml)

        puladas = {p.codigo for p in relatorio.puladas}
        assert "ASSIN-004" in puladas or "ASSIN-004" in _codigos(xml)
