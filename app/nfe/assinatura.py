"""Assinatura da NF-e: RSA-SHA1 e C14N inclusiva, porque o leiaute os exige.

**Isto não é escolha nossa.** O XSD oficial (`xmldsig-core-schema_v1.01.xsd`, que
acompanha o `nfe_v4.00.xsd`) declara os atributos como `fixed`:

    CanonicalizationMethod/@Algorithm = http://www.w3.org/TR/2001/REC-xml-c14n-20010315
    SignatureMethod/@Algorithm        = http://www.w3.org/2000/09/xmldsig#rsa-sha1

e o `Transform` só aceita `enveloped-signature` e a C14N inclusiva. Ou seja: SHA-256,
que é o padrão seguro e o que a NFS-e usa, **não valida** no schema da NF-e.

O `signxml` recusa SHA-1 de propósito (`check_deprecated_methods`), e a recusa está
certa como padrão. Aqui ela é desligada por uma razão específica e documentada: um
documento fiscal cujo schema fixa o algoritmo. A subclasse existe para que o desvio
fique isolado neste módulo, visível, e não espalhado pelo assinador do projeto.

Limite declarado: SHA-1 é criptograficamente quebrado para colisão. Para assinatura
digital com chave privada o risco prático é menor, mas não é zero — quem mantém o
leiaute é que decide, e a decisão não é nossa.
"""

from __future__ import annotations

from lxml import etree
from signxml import (
    CanonicalizationMethod,
    DigestAlgorithm,
    SignatureMethod,
    XMLSigner,
)

from app.certificates.cofre import CertificadoA1
from app.nfse.constants import NS_DSIG
from app.nfse.signer import ErroAssinatura


class _AssinadorNFe(XMLSigner):
    """`XMLSigner` que aceita SHA-1 porque o schema da NF-e o exige."""

    def check_deprecated_methods(self) -> None:
        # Sem `super()`: a guarda existe para proteger quem escolhe algoritmo por
        # conveniência. Aqui o algoritmo é imposto pelo XSD oficial da NF-e.
        return None


def _primeiro_com_id(raiz: etree._Element) -> etree._Element | None:
    for elemento in raiz.iter():
        if isinstance(elemento.tag, str) and elemento.get("Id"):
            return elemento
    return None


def assinar_nfe(xml: bytes, certificado: CertificadoA1) -> bytes:
    """Assina a NF-e no padrão que o leiaute 4.00 exige."""
    try:
        raiz = etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        raise ErroAssinatura(f"NF-e mal formada para assinatura: {exc}") from exc

    alvo = _primeiro_com_id(raiz)
    if alvo is None:
        raise ErroAssinatura("NF-e sem atributo Id em infNFe")

    chave_pem, cadeia = certificado.material_para_assinatura()

    assinador = _AssinadorNFe(
        signature_algorithm=SignatureMethod.RSA_SHA1,
        digest_algorithm=DigestAlgorithm.SHA1,
        c14n_algorithm=CanonicalizationMethod.CANONICAL_XML_1_0,
    )
    # Mesma limitação de tipagem da NFS-e: namespace default usa a chave None.
    assinador.namespaces = {None: NS_DSIG}  # type: ignore[dict-item]

    try:
        assinado = assinador.sign(
            raiz,
            key=chave_pem,
            # Como na NFS-e: só o certificado folha. Cadeia inteira no KeyInfo faz
            # a SEFAZ recusar a assinatura.
            cert=cadeia[:1],
            reference_uri=f"#{alvo.get('Id')}",
            always_add_key_value=False,
        )
    except Exception as exc:  # a biblioteca levanta tipos próprios
        raise ErroAssinatura(f"falha ao assinar a NF-e: {exc}") from exc

    corpo = etree.tostring(etree.fromstring(etree.tostring(assinado)))
    return b'<?xml version="1.0" encoding="UTF-8"?>' + corpo
