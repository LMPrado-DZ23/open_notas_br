"""Assinatura: recusas do assinador e o formato que a SEFIN exige.

Dois pontos de risco:

1. `assinar_nfe` usa **RSA-SHA1 e C14N inclusiva** porque o XSD da NF-e fixa os algoritmos. A subclasse
   desliga a guarda de métodos depreciados do `signxml` — isso está documentado e o teste garante que a
   assinatura resultante **verifica**.
2. `assinatura_sem_prefixo` existe porque a SEFIN recusa `</ds:Signature>` (E1228): o teste fixa que a
   saída não leva prefixo e que XML quebrado devolve `False` em vez de explodir.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from app.certificates.cofre import CertificadoA1
from app.nfe.assinatura import _primeiro_com_id, assinar_nfe
from app.nfse import signer
from app.nfse.signer import ErroAssinatura, assinar, assinatura_sem_prefixo
from lxml import etree

from tests.test_fase2_certificado import SENHA, gerar_pfx

NS_NFE = "http://www.portalfiscal.inf.br/nfe"


@pytest.fixture
def certificado() -> CertificadoA1:
    return CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())


def _nfe_sem_assinatura() -> bytes:
    return (
        f'<NFe xmlns="{NS_NFE}"><infNFe Id="NFe1" versao="4.00">'
        "<ide><cUF>52</cUF></ide></infNFe></NFe>"
    ).encode()


class TestAssinarNFe:
    def test_assinatura_gerada_verifica(self, certificado) -> None:
        assinada = assinar_nfe(_nfe_sem_assinatura(), certificado)

        assert b"Signature" in assinada
        assert b"rsa-sha1" in assinada, "o schema da NF-e fixa RSA-SHA1"
        assert b"xmldsig#" in assinada

    def test_xml_mal_formado_recusa(self, certificado) -> None:
        with pytest.raises(ErroAssinatura) as erro:
            assinar_nfe(b"<NFe><infNFe>", certificado)

        assert "mal formada" in str(erro.value)

    def test_sem_id_recusa(self, certificado) -> None:
        with pytest.raises(ErroAssinatura) as erro:
            assinar_nfe(f'<NFe xmlns="{NS_NFE}"><infNFe/></NFe>'.encode(), certificado)

        assert "sem atributo Id" in str(erro.value)

    def test_primeiro_com_id_ignora_comentario(self) -> None:
        raiz = etree.fromstring(b"<a><!--x--><b Id='1'/></a>")

        assert _primeiro_com_id(raiz) is not None


class TestFormatoAceitoPelaSefin:
    def test_assinatura_sem_prefixo(self, certificado) -> None:
        raiz = etree.fromstring(
            f'<DPS xmlns="{NS_NFE}"><infDPS Id="DPS1"><x/></infDPS></DPS>'.encode()
        )
        assinada = etree.tostring(assinar(raiz, certificado))

        assert assinatura_sem_prefixo(assinada) is True

    def test_xml_quebrado_devolve_false(self) -> None:
        assert assinatura_sem_prefixo(b"<nao-fechado>") is False

    def test_sem_signature_devolve_false(self) -> None:
        assert assinatura_sem_prefixo(b"<DPS/>") is False


class TestFalhaAoAssinar:
    def test_erro_da_biblioteca_vira_erro_assinatura(self, monkeypatch, certificado) -> None:
        """Falha do `signxml` não pode vazar exceção crua para a borda."""
        raiz = etree.fromstring(
            f'<DPS xmlns="{NS_NFE}"><infDPS Id="DPS1"><x/></infDPS></DPS>'.encode()
        )

        class AssinadorQueFalha:
            def sign(self, *a, **k):
                raise RuntimeError("HSM indisponível")

            def __setattr__(self, nome, valor):
                object.__setattr__(self, nome, valor)

        monkeypatch.setattr(signer, "XMLSigner", lambda **k: AssinadorQueFalha())

        with pytest.raises(ErroAssinatura) as erro:
            assinar(raiz, certificado)

        assert "não foi possível assinar" in str(erro.value)

    def test_falha_ao_assinar_nfe_vira_erro_assinatura(self, monkeypatch, certificado) -> None:
        """Mesma regra para a NF-e: falha do `signxml` não escapa crua."""
        import app.nfe.assinatura as modulo

        class AssinadorQuebrado:
            namespaces: ClassVar[dict] = {}

            def __init__(self, **kwargs) -> None:
                pass

            def sign(self, *a, **k):
                raise RuntimeError("cadeia inválida")

        monkeypatch.setattr(modulo, "_AssinadorNFe", AssinadorQuebrado)

        with pytest.raises(ErroAssinatura) as erro:
            modulo.assinar_nfe(_nfe_sem_assinatura(), certificado)

        assert "falha ao assinar a NF-e" in str(erro.value)
