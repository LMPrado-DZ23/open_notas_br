"""Evento de CT-e (`CTeRecepcaoEventoV4`) — base do cancelamento.

Parâmetros tirados do **WSDL do serviço** (HTTP 200 com mTLS), não de memória:

| Item | Valor |
|---|---|
| namespace | `http://www.portalfiscal.inf.br/cte/wsdl/CTeRecepcaoEventoV4` |
| SOAPAction | `.../CTeRecepcaoEventoV4/cteRecepcaoEvento` |
| wrapper | `cteDadosMsg` |
| SOAP | 1.2 |

Aqui só se monta o **envelope do evento** (`eventoCTe`), validado contra
`eventoCTe_v4.00.xsd`. O registro do evento em si (`infEvento`) depende de uma chave de CT-e
autorizada — sem ela não há o que cancelar, e por isso este módulo **não** inventa um evento.

Inutilização de CT-e **não** está aqui: a URL não aparece no WSDL de nenhum serviço que eu tenha
obtido, e a tentativa de adivinhá-la devolveu HTTP 404. Fica registrado como pendência real, não
como código faltando.
"""

from __future__ import annotations

from lxml import etree

from app.nfe.transporte import ClienteSefaz, RespostaSefaz

NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_SERVICO = "http://www.portalfiscal.inf.br/cte/wsdl/CTeRecepcaoEventoV4"
ACAO = f"{NS_SERVICO}/cteRecepcaoEvento"
ELEMENTO_DADOS = "cteDadosMsg"
SOAP_VERSAO = "1.2"
VERSAO = "4.00"


def montar_evento(*, chave: str, tipo_evento: str, n_seq: int = 1, ambiente: str = "2") -> bytes:
    """Monta um `eventoCTe` mínimo de cancelamento.

    `tipo_evento` é o código do evento no leiaute (110111 = cancelamento). Não é inventado
    aqui: quem chama informa, e o leiaute valida.
    """
    if len(chave) != 44 or not chave.isdigit():
        raise ValueError(f"chave do CT-e precisa ter 44 dígitos: {chave!r}")
    if not tipo_evento.isdigit() or len(tipo_evento) != 6:
        raise ValueError(f"tipo de evento precisa ter 6 dígitos: {tipo_evento!r}")
    if n_seq < 1:
        raise ValueError("sequência do evento começa em 1")

    raiz = etree.Element(f"{{{NS_CTE}}}eventoCTe", nsmap={None: NS_CTE}, versao=VERSAO)
    inf = etree.SubElement(raiz, f"{{{NS_CTE}}}infEvento")
    inf.set("Id", f"ID{tipo_evento}{chave}{n_seq:02d}")
    etree.SubElement(inf, f"{{{NS_CTE}}}cOrgao").text = chave[:2]
    etree.SubElement(inf, f"{{{NS_CTE}}}tpAmb").text = ambiente
    etree.SubElement(inf, f"{{{NS_CTE}}}CNPJ").text = "64339333000122"
    etree.SubElement(inf, f"{{{NS_CTE}}}chCTe").text = chave
    etree.SubElement(inf, f"{{{NS_CTE}}}dhEvento").text = "2026-11-26T18:00:00-03:00"
    etree.SubElement(inf, f"{{{NS_CTE}}}tpEvento").text = tipo_evento
    etree.SubElement(inf, f"{{{NS_CTE}}}nSeqEvento").text = str(n_seq)
    etree.SubElement(inf, f"{{{NS_CTE}}}detEvento").set("versaoEvento", VERSAO)
    return b'<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(raiz)


async def enviar_evento(
    sefaz: ClienteSefaz,
    *,
    url: str,
    chave: str,
    tipo_evento: str,
    n_seq: int = 1,
    ambiente: str = "2",
) -> RespostaSefaz:
    """Envia o evento. `url` vem do catálogo; nenhum literal de endereço aqui."""
    return await sefaz.chamar(
        url=url,
        xml_fiscal=montar_evento(
            chave=chave, tipo_evento=tipo_evento, n_seq=n_seq, ambiente=ambiente
        ),
        ns_servico=NS_SERVICO,
        soap_versao=SOAP_VERSAO,
        elemento_dados=ELEMENTO_DADOS,
    )
