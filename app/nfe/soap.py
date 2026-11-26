"""Envelope SOAP 1.2 para os webservices da SEFAZ.

Construir e desmontar o envelope **não** exige credenciamento — só a chamada exige. Isso
permite ter a camada pronta e verificada contra os schemas oficiais antes de qualquer
transmissão.

O formato é o do `nfeDadosMsg`: o XML da NF-e (ou do lote, ou da consulta) vai **dentro**
do `Body`, sem assinatura adicional — a assinatura já está no documento fiscal, e assinar
o envelope seria assinatura dupla que a SEFAZ recusa.

**Nada de URL aqui.** Endpoint vem da tabela `webservices_sefaz` (R3), e este módulo não
conhece nenhum.
"""

from __future__ import annotations

from lxml import etree

NS_SOAP12 = "http://www.w3.org/2003/05/soap-envelope"
NS_NFE = "http://www.portalfiscal.inf.br/nfe"

#: Nome do elemento que carrega o XML fiscal no corpo. É fixo no leiaute.
ELEMENTO_DADOS = "nfeDadosMsg"


class ErroSOAP(Exception):
    """Envelope malformado ou resposta sem corpo reconhecível."""


def envelopar(xml_fiscal: bytes, *, versao: str = "4.00") -> bytes:
    """Embrulha o XML fiscal num envelope SOAP 1.2.

    O `versao` fica no documento fiscal, não no envelope: o envelope SOAP 1.2 não tem
    atributo de versão de leiaute.
    """
    try:
        dados = etree.fromstring(xml_fiscal)
    except etree.XMLSyntaxError as exc:
        raise ErroSOAP(f"XML fiscal inválido: {exc}") from exc

    envelope = etree.Element(f"{{{NS_SOAP12}}}Envelope", nsmap={"soap12": NS_SOAP12, "nfe": NS_NFE})
    corpo = etree.SubElement(envelope, f"{{{NS_SOAP12}}}Body")
    dados_msg = etree.SubElement(corpo, f"{{{NS_NFE}}}{ELEMENTO_DADOS}")
    dados_msg.append(dados)

    return b'<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(envelope)


def desenvelopar(resposta: bytes) -> etree._Element:
    """Extrai o primeiro elemento do `Body`.

    Devolve o elemento fiscal cru (`retConsStatServ`, `retEnviNFe`, `retConsReciNFe`...).
    A validação contra o schema do serviço é responsabilidade de quem chamou, porque o
    schema depende de qual operação foi feita.
    """
    try:
        raiz = etree.fromstring(resposta)
    except etree.XMLSyntaxError as exc:
        raise ErroSOAP(f"resposta não é XML: {exc}") from exc

    corpo = raiz.find(f".//{{{NS_SOAP12}}}Body")
    if corpo is None or len(corpo) == 0:
        # Também acontece quando a SEFAZ devolve SOAP 1.1 ou um HTML de erro de gateway.
        raise ErroSOAP("resposta sem Body SOAP 1.2 com conteúdo")

    elemento = corpo[0]

    # Os WSDLs da NF-e embrulham o retorno em `nfeResultMsg`; o leiaute começa no filho.
    # Descoberto com resposta REAL da SEFAZ-GO: sem este salto, `ler()` recusava com
    # "elemento não é retorno da SEFAZ: nfeResultMsg" e o ciclo de autorização quebrava contra
    # o autorizador de verdade — os fixtures feitos em casa não tinham o embrulho.
    if etree.QName(elemento).localname.endswith("ResultMsg") and len(elemento) > 0:
        elemento = elemento[0]

    return elemento


def extrair_falha(resposta: bytes) -> dict[str, str] | None:
    """Lê um `soap:Fault`, se houver.

    SEFAZ devolve Fault para erro de infraestrutura. Devolver `None` significa "não é
    Fault", e **não** "deu certo" — quem chama precisa olhar o conteúdo do Body.
    """
    try:
        raiz = etree.fromstring(resposta)
    except etree.XMLSyntaxError:
        return None

    falha = raiz.find(f".//{{{NS_SOAP12}}}Fault")
    if falha is None:
        return None

    def _texto(tag: str) -> str:
        elemento = falha.find(f".//{{{NS_SOAP12}}}{tag}")
        if elemento is None:
            elemento = falha.find(f".//{tag}")
        return (elemento.text or "").strip() if elemento is not None else ""

    return {
        "code": _texto("Value") or _texto("faultcode"),
        "reason": _texto("Text") or _texto("faultstring"),
    }
