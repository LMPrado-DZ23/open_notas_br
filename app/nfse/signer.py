"""Assinatura XMLDSig da DPS e de pedidos de evento.

Contrato confirmado na implementação de referência (`docs/REFERENCIAS.md`, seção 7):

- **Enveloped**, **RSA-SHA256**, digest **SHA-256**.
- Referência ao ``Id`` do elemento ``inf*`` (``URI="#DPS..."``), não ao documento.
- **Sem prefixo de namespace** na tag ``Signature``: a SEFIN rejeita prefixo
  (código E1228). Por isso ``namespaces = {None: NS_DSIG}`` e reparse depois.
- **Canonicalização exclusiva** (C14N exclusiva), a mesma que a SEFIN usa nos
  XMLs de retorno. Se a homologação recusar a assinatura, o primeiro suspeito é
  este parâmetro: trocar por C14N 1.0 antes de duvidar da chave.

Por que `signxml` e não `lxml` + `cryptography` na mão: implementar canonicalização
e montagem de `SignedInfo` corretamente é a causa mais comum de "assinatura
recusada" em XMLDSig. A dependência é pequena e o erro é silencioso — vale usar
biblioteca testada.
"""

from __future__ import annotations

import logging

from lxml import etree
from signxml import (
    CanonicalizationMethod,
    DigestAlgorithm,
    SignatureMethod,
    XMLSigner,
    XMLVerifier,
)

from app.certificates.cofre import CertificadoA1
from app.nfse.constants import NS_DSIG

logger = logging.getLogger(__name__)

#: C14N do projeto. **Exclusive com comentários** (`#WithComments`) porque é o que
#: a NFS-e Nacional usa: comparado com o documento válido de referência
#: (`nfse_valido_com_IBSCBS.xml`, repo calculadora-rtc-regime-regular), a
#: assinatura usa `http://www.w3.org/2001/10/xml-exc-c14n#WithComments` tanto em
#: `CanonicalizationMethod` quanto no `Transform`. Assinar com exclusive SEM
#: comentários faz a SEFIN recusar com **E0714** ("Arquivo enviado com erro na
#: assinatura"). Ver docs/REFERENCIAS.md §14.
C14N = CanonicalizationMethod.EXCLUSIVE_XML_CANONICALIZATION_1_0_WITH_COMMENTS
#: Alternativa a testar em homologação caso a SEFIN recuse a assinatura.
C14N_ALTERNATIVA = CanonicalizationMethod.CANONICAL_XML_1_0


class ErroAssinatura(Exception):
    """Falha ao assinar ou verificar o XML."""


def _primeiro_com_id(raiz: etree._Element) -> etree._Element | None:
    for elemento in raiz:
        if elemento.get("Id"):
            return elemento
    return None


def assinar(
    raiz: etree._Element,
    certificado: CertificadoA1,
    *,
    id_elemento: str | None = None,
    c14n: CanonicalizationMethod = C14N,
) -> etree._Element:
    """Assina `raiz` referenciando o `Id` do primeiro filho que tiver um.

    Devolve a árvore assinada já reparseada, para que o elemento `Signature`
    exista de fato no namespace XMLDSig em memória — sem o reparse, a árvore fica
    inconsistente e a validação de schema não enxerga a assinatura.
    """
    alvo = _primeiro_com_id(raiz)
    if alvo is None:
        raise ErroAssinatura("nenhum elemento com atributo Id para assinar")
    id_alvo = id_elemento or alvo.get("Id")

    chave_pem, cadeia = certificado.material_para_assinatura()

    assinador = XMLSigner(
        signature_algorithm=SignatureMethod.RSA_SHA256,
        digest_algorithm=DigestAlgorithm.SHA256,
        c14n_algorithm=c14n,
    )
    assinador.namespaces = {None: NS_DSIG}

    try:
        assinado = assinador.sign(
            raiz,
            key=chave_pem,
            cert=cadeia,
            reference_uri=f"#{id_alvo}",
            always_add_key_value=False,
        )
    except Exception as exc:  # a biblioteca levanta tipos próprios
        logger.exception("falha_ao_assinar_xml")
        raise ErroAssinatura(f"não foi possível assinar: {exc}") from exc

    return etree.fromstring(etree.tostring(assinado))


def assinar_bytes(
    xml: bytes, certificado: CertificadoA1, *, c14n: CanonicalizationMethod = C14N
) -> bytes:
    """Assina um XML serializado e devolve os bytes assinados.

    A declaração XML é recolocada à mão: `etree.tostring` **descarta** a declaração
    ao re-serializar, e sem ela a SEFIN recusa com E1229 ("Xml não está utilizando
    codificação UTF-8") — ela usa a declaração para detectar a codificação.

    As aspas são duplas de propósito: o validador procura `encoding="UTF-8"`
    literal, e `xml_declaration=True` do lxml emite aspas simples.

    Dois erros reais, descobertos na primeira emissão em Produção Restrita.
    """
    try:
        raiz = etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        raise ErroAssinatura(f"XML mal formado para assinatura: {exc}") from exc
    corpo = etree.tostring(assinar(raiz, certificado, c14n=c14n))
    return b'<?xml version="1.0" encoding="UTF-8"?>' + corpo


def assinar_dps(dps_xml: bytes, certificado: CertificadoA1) -> bytes:
    """Assina uma DPS montada por `app.nfse.dps`."""
    return assinar_bytes(dps_xml, certificado)


def verificar(xml: bytes | etree._Element, certificado: CertificadoA1 | None = None) -> bool:
    """Verifica a assinatura e devolve ``True``/``False``.

    **Atenção ao retorno**: esta função não levanta exceção quando a assinatura é
    inválida — ela devolve ``False``. Quem chama e ignora o retorno trata
    documento adulterado como válido. Verificado na prática: um script de
    diagnóstico escreveu `verificar(xml, cert)` sem usar o resultado e concluiu
    "adulteração aceita". Para fluxo onde falhar precisa ser impossível de
    ignorar, use :func:`exigir_assinatura_valida`.

    Usar em teste e em diagnóstico. **Não** valida cadeia ICP-Brasil nem
    revogação: prova integridade em relação àquele certificado, nada além.
    """
    dados = xml if isinstance(xml, bytes) else etree.tostring(xml)
    if certificado is None:
        raise ErroAssinatura("verificação exige o certificado para confirmar a assinatura")

    _, cadeia = certificado.material_para_assinatura()
    try:
        XMLVerifier().verify(
            dados,
            x509_cert="\n".join(cadeia),
            ignore_ambiguous_key_info=True,
        )
    except Exception as exc:  # a biblioteca levanta tipos próprios
        logger.warning("assinatura_invalida", extra={"erro": type(exc).__name__})
        return False
    return True


def exigir_assinatura_valida(xml: bytes | etree._Element, certificado: CertificadoA1) -> None:
    """Como :func:`verificar`, mas levanta quando a assinatura não confere.

    Existe porque `verificar` devolve booleano, e booleano ignorado vira falso
    positivo silencioso. Em caminho fiscal — aceitar documento de terceiro,
    conferir XML recebido — a falha precisa ser impossível de ignorar.
    """
    if not verificar(xml, certificado):
        raise ErroAssinatura(
            "assinatura XMLDSig não confere: o documento foi alterado depois de "
            "assinado ou foi assinado com outro certificado"
        )


def assinatura_sem_prefixo(xml: bytes) -> bool:
    """True se a tag `Signature` sai no formato que a SEFIN aceita.

    A SEFIN rejeita `</ds:Signature>` e afins (E1228). Este teste existe porque é
    fácil gerar o XML com prefixo sem perceber, e o erro só aparece em homologação.
    """
    try:
        raiz = etree.fromstring(xml)
    except etree.XMLSyntaxError:
        return False
    for elemento in raiz.iter():
        if etree.QName(elemento).localname == "Signature":
            return not elemento.prefix
    return False
