"""Regras de assinatura digital (XMLDSig envelopado).

Duas camadas, com garantias bem diferentes:

1. **Estrutural** (sempre roda): existe ``Signature``? ``Reference/@URI`` aponta
   para o ``Id`` do documento? ``DigestValue``/``SignatureValue`` estão
   preenchidos e são base64 plausível?
2. **Criptográfica** (só com o extra ``notasbr[assinatura]``): o digest confere e
   a assinatura valida contra o certificado embutido.

**O que nem a camada 2 prova:** que o certificado pertence à ICP-Brasil, que não
está revogado, e que o emitente é quem diz ser. Cadeia de confiança não é
validada aqui. Isso está declarado nas limitações do relatório.

Os achados usam o caminho absoluto do elemento (``nfeProc/NFe/Signature``), não o
caminho relativo ao corpo, porque ``Signature`` é irmão de ``infNFe``.
"""

from __future__ import annotations

import base64
import binascii
from xml.etree import ElementTree as ET

from ..xml_util import local, namespace, texto
from .base import Contexto, regra

NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"


def _assinatura(ctx: Contexto) -> ET.Element | None:
    """Elemento ``Signature`` do documento, se existir."""
    for elemento in ctx.raiz.iter():
        if local(elemento.tag) == "Signature":
            return elemento
    return None


def _descendente(pai: ET.Element, nome: str) -> ET.Element | None:
    for elemento in pai.iter():
        if local(elemento.tag) == nome:
            return elemento
    return None


@regra("ASSIN-001", "Documento assinado (elemento Signature presente)", ("nfe", "cte"))
def presenca(ctx: Contexto) -> None:
    assinatura = _assinatura(ctx)
    if assinatura is None:
        ctx.erro(
            "ASSIN-001",
            "documento sem elemento Signature: não há assinatura digital",
            "",
        )
        return
    ns = namespace(assinatura.tag)
    if ns != NS_DSIG:
        ctx.aviso_em(
            "ASSIN-001",
            f"namespace da Signature é {ns!r}, esperado {NS_DSIG!r}",
            assinatura,
            namespace=ns,
        )


@regra("ASSIN-002", "Reference aponta para o Id do documento", ("nfe", "cte"))
def referencia(ctx: Contexto) -> None:
    assinatura = _assinatura(ctx)
    if assinatura is None:
        ctx.pular("ASSIN-002", "documento sem Signature")
        return
    referencia_elem = _descendente(assinatura, "Reference")
    if referencia_elem is None:
        ctx.erro_em("ASSIN-002", "Signature sem elemento Reference", assinatura)
        return
    uri = referencia_elem.get("URI")
    id_documento = ctx.corpo.get("Id")
    if not uri:
        ctx.erro_em("ASSIN-002", "Reference sem atributo URI", referencia_elem)
        return
    if not id_documento:
        ctx.pular("ASSIN-002", "documento sem atributo Id para conferir")
        return
    if uri != f"#{id_documento}":
        ctx.erro_em(
            "ASSIN-002",
            f"Reference URI é {uri!r}, mas o Id do documento é {id_documento!r}",
            referencia_elem,
            uri=uri,
            id=id_documento,
        )


@regra("ASSIN-003", "DigestValue e SignatureValue preenchidos", ("nfe", "cte"))
def valores(ctx: Contexto) -> None:
    assinatura = _assinatura(ctx)
    if assinatura is None:
        ctx.pular("ASSIN-003", "documento sem Signature")
        return
    for nome in ("DigestValue", "SignatureValue"):
        elemento = _descendente(assinatura, nome)
        valor = texto(elemento)
        if valor is None:
            ctx.erro_em(
                "ASSIN-003",
                f"{nome} vazio ou ausente na Signature",
                elemento if elemento is not None else assinatura,
                campo=nome,
            )
            continue
        try:
            decodificado = base64.b64decode(valor, validate=True)
        except (binascii.Error, ValueError):
            ctx.erro_em(
                "ASSIN-003",
                f"{nome} não é base64 válido",
                elemento,
                campo=nome,
            )
            continue
        if len(decodificado) not in (20, 32, 48, 64):
            ctx.aviso_em(
                "ASSIN-003",
                f"{nome} decodifica para {len(decodificado)} bytes, tamanho atípico "
                "para SHA-1/SHA-256",
                elemento,
                campo=nome,
                bytes=len(decodificado),
            )


@regra("ASSIN-004", "Assinatura confere criptograficamente", ("nfe", "cte"))
def verificacao_criptografica(ctx: Contexto) -> None:
    """Verifica o XMLDSig contra o certificado embutido no próprio documento."""
    assinatura = _assinatura(ctx)
    if assinatura is None:
        ctx.pular("ASSIN-004", "documento sem Signature")
        return

    try:  # imports opcionais: o núcleo não depende deles
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding
        from lxml import etree
        from signxml import XMLVerifier
    except ImportError:
        ctx.pular(
            "ASSIN-004",
            "verificação criptográfica indisponível: instale notasbr[assinatura]",
        )
        return

    certificado = texto(_descendente(assinatura, "X509Certificate"))
    if not certificado:
        ctx.pular("ASSIN-004", "Signature sem X509Certificate; não há como verificar")
        return

    try:
        der = base64.b64decode(certificado, validate=True)
        certificado_obj = x509.load_der_x509_certificate(der)
        pem = certificado_obj.public_bytes(Encoding.PEM)
    except (binascii.Error, ValueError) as exc:
        ctx.erro_em(
            "ASSIN-004",
            f"certificado embutido não pôde ser lido: {exc}",
            assinatura,
        )
        return

    try:
        raiz_lxml = etree.fromstring(ET.tostring(ctx.raiz))
        XMLVerifier().verify(raiz_lxml, x509_cert=pem, expect_references=1)
    except Exception as exc:  # a biblioteca levanta tipos próprios
        ctx.erro_em(
            "ASSIN-004",
            f"assinatura NÃO confere com o certificado embutido: {exc}",
            assinatura,
            erro=type(exc).__name__,
        )
        return

    ctx.info_em(
        "ASSIN-004",
        "assinatura íntegra contra o certificado embutido; cadeia ICP-Brasil não foi validada",
        assinatura,
    )


@regra("ASSIN-005", "Certificado do assinante presente", ("nfe", "cte"))
def certificado_presente(ctx: Contexto) -> None:
    assinatura = _assinatura(ctx)
    if assinatura is None:
        ctx.pular("ASSIN-005", "documento sem Signature")
        return
    if _descendente(assinatura, "X509Certificate") is None:
        ctx.aviso_em(
            "ASSIN-005",
            "Signature sem X509Certificate: não é possível conferir a autoria",
            assinatura,
        )
