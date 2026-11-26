"""Consulta de status do MDF-e (`MDFeStatusServico`).

Três valores que a SEFAZ exige e que **não** estão no XSD do leiaute vieram do WSDL do serviço,
medidos com chamada real (auditoria §31):

| Item | Valor |
|---|---|
| namespace do serviço | `http://www.portalfiscal.inf.br/mdfe/wsdl/MDFeStatusServico` |
| SOAPAction | `.../MDFeStatusServico/mdfeStatusServicoMDF` |
| wrapper do pedido | `mdfeDadosMsg` |
| versão SOAP | **1.2** (o WSDL de MDF-e só declara `soap12:binding`) |

Resultado verificado: `cStat 107 — Serviço em Operação` no SVRS para ES.

Diferença em relação ao CT-e: o `consStatServMDFe` **não** leva `cUF` (o de CT-e leva) e o
leiaute é 3.00, não 4.00 — ambos conferidos no XSD, não por tentativa.
"""

from __future__ import annotations

from lxml import etree

from app.nfe.transporte import ClienteSefaz, RespostaSefaz

NS_MDFE = "http://www.portalfiscal.inf.br/mdfe"
NS_SERVICO = "http://www.portalfiscal.inf.br/mdfe/wsdl/MDFeStatusServico"
ACAO = f"{NS_SERVICO}/mdfeStatusServicoMDF"
ELEMENTO_DADOS = "mdfeDadosMsg"
SOAP_VERSAO = "1.2"
VERSAO = "3.00"


def montar_cons_stat_serv_mdfe(*, ambiente: str = "2") -> bytes:
    """Monta o `consStatServMDFe`.

    Sem `cUF`: o serviço de MDF-e é por autorizador, e o XSD não pede UF — diferente do CT-e.
    """
    if ambiente not in ("1", "2"):
        raise ValueError(f"ambiente precisa ser '1' (produção) ou '2' (homologação): {ambiente!r}")

    raiz = etree.Element(f"{{{NS_MDFE}}}consStatServMDFe", nsmap={None: NS_MDFE}, versao=VERSAO)
    etree.SubElement(raiz, f"{{{NS_MDFE}}}tpAmb").text = ambiente
    etree.SubElement(raiz, f"{{{NS_MDFE}}}xServ").text = "STATUS"
    return b'<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(raiz)


async def consultar_status(sefaz: ClienteSefaz, *, url: str, ambiente: str = "2") -> RespostaSefaz:
    """Consulta o status do serviço de MDF-e. `url` vem do catálogo, nunca de literal aqui."""
    return await sefaz.chamar(
        url=url,
        xml_fiscal=montar_cons_stat_serv_mdfe(ambiente=ambiente),
        ns_servico=NS_SERVICO,
        soap_versao=SOAP_VERSAO,
        elemento_dados=ELEMENTO_DADOS,
    )
