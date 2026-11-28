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
#: SOAP 1.1 — exigido por endpoints `.asmx` do SVRS/SEFAZ-SP. Medido: com 1.2 o SVRS
#: responde 215 "Falha no schema XML"; com 1.1 aceita e devolve o retorno fiscal.
NS_SOAP11 = "http://schemas.xmlsoap.org/soap/envelope/"
NS_NFE = "http://www.portalfiscal.inf.br/nfe"

#: Nome do elemento que carrega o XML fiscal no corpo. É fixo no leiaute.
ELEMENTO_DADOS = "nfeDadosMsg"


class ErroSOAP(Exception):
    """Envelope malformado ou resposta sem corpo reconhecível."""


def envelopar(
    xml_fiscal: bytes,
    *,
    versao: str = "4.00",
    ns_servico: str | None = None,
    soap_versao: str = "1.2",
    elemento_dados: str | None = None,
) -> bytes:
    """Embrulha o XML fiscal num envelope SOAP 1.1 ou 1.2.

    O `versao` fica no documento fiscal, não no envelope: o envelope SOAP 1.2 não tem
    atributo de versão de leiaute.
    """
    try:
        dados = etree.fromstring(xml_fiscal)
    except etree.XMLSyntaxError as exc:
        raise ErroSOAP(f"XML fiscal inválido: {exc}") from exc

    ns_soap, prefixo = (NS_SOAP11, "soap") if soap_versao == "1.1" else (NS_SOAP12, "soap12")
    # Sem declarar o prefixo `nfe` no envelope: se ele existe, o lxml serializa o XML
    # fiscal como `<nfe:consStatServ>` em vez de namespace padrão, e o SVRS recusa com
    # 215 "Falha no schema XML". Medido: sem o prefixo, o mesmo pedido passa.
    envelope = etree.Element(f"{{{ns_soap}}}Envelope", nsmap={prefixo: ns_soap})
    corpo = etree.SubElement(envelope, f"{{{ns_soap}}}Body")
    # O wrapper vive no namespace **do serviço** (`.../wsdl/NFeStatusServico4`), não no fiscal.
    # Medido: GO aceita o namespace fiscal, SVRS responde 242 "Mensagem SOAP inválida".
    # O nome do wrapper é do WSDL do serviço, não do leiaute: NF-e usa `nfeDadosMsg` e CT-e usa
    # `cteDadosMsg`. Medido: com o nome de NF-e no serviço de CT-e, a SEFAZ responde 243
    # "XML Mal Formado"; com o nome certo, 107 "Serviço em Operação".
    dados_msg = etree.SubElement(
        corpo, f"{{{ns_servico or NS_NFE}}}{elemento_dados or ELEMENTO_DADOS}"
    )
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

    # A resposta pode vir em SOAP 1.2 (GO, endpoints `.svc`) ou 1.1 (SVRS/SEFAZ-SP, `.asmx`).
    # Procurar só em 1.2 fazia a resposta do SVRS falhar com "não é XML".
    corpo = raiz.find(f".//{{{NS_SOAP12}}}Body")
    if corpo is None:
        corpo = raiz.find(f".//{{{NS_SOAP11}}}Body")
    if corpo is None or len(corpo) == 0:
        # Também acontece quando a SEFAZ devolve um HTML de erro de gateway.
        raise ErroSOAP("resposta sem Body SOAP com conteúdo")

    elemento = corpo[0]

    # Os WSDLs da NF-e embrulham o retorno em `nfeResultMsg`; o leiaute começa no filho.
    # Descoberto com resposta REAL da SEFAZ-GO: sem este salto, `ler()` recusava com
    # "elemento não é retorno da SEFAZ: nfeResultMsg" e o ciclo de autorização quebrava contra
    # o autorizador de verdade — os fixtures feitos em casa não tinham o embrulho.
    # NF-e embrulha em `nfeResultMsg`; CT-e embrulha em `cteStatusServicoCTResult`.
    # Ambos precisam ser saltados: o leiaute começa no filho.
    local = etree.QName(elemento).localname
    if (local.endswith("ResultMsg") or local.endswith("Result")) and len(elemento) > 0:
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

    # SOAP 1.2 (autorizadores estaduais) e SOAP 1.1 (SVRS/SP em `.asmx`). Procurar só no
    # namespace 1.2 deixava o Fault de 1.1 passar como resposta normal: o erro virava
    # `ErroDeRetorno("elemento não é retorno da SEFAZ: Fault")`, que não é classificado como
    # definitivo — risco de retry indevido sobre uma falha que não vai melhorar.
    falha = raiz.find(f".//{{{NS_SOAP12}}}Fault")
    if falha is None:
        falha = raiz.find(f".//{{{NS_SOAP11}}}Fault")
    if falha is None:
        falha = raiz.find(".//Fault")  # sem namespace, como alguns retornam
    if falha is None:
        return None

    def _texto(tag: str) -> str:
        elemento = falha.find(f".//{{{NS_SOAP12}}}{tag}")
        if elemento is None:
            elemento = falha.find(f".//{{{NS_SOAP11}}}{tag}")
        if elemento is None:
            elemento = falha.find(f".//{tag}")
        return (elemento.text or "").strip() if elemento is not None else ""

    return {
        "code": _texto("Value") or _texto("faultcode"),
        "reason": _texto("Text") or _texto("faultstring"),
    }
