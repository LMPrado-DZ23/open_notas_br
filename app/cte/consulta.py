"""Consulta de status do CT-e (`CTeStatusServicoV4`).

Os três valores que a SEFAZ exige e que **não** estão no XSD do leiaute vieram do WSDL do
serviço, medidos com chamada real (auditoria §31):

| Item | Valor |
|---|---|
| namespace do serviço | `http://www.portalfiscal.inf.br/cte/wsdl/CTeStatusServicoV4` |
| SOAPAction | `.../CTeStatusServicoV4/cteStatusServicoCT` |
| wrapper do pedido | `cteDadosMsg` (NF-e usa `nfeDadosMsg` — trocar dá `243 XML Mal Formado`) |
| versão SOAP | **1.2** (com 1.1 o SVRS devolve HTTP 500) |

Resultado verificado: `cStat 107 — Serviço em Operação` no SVRS para ES.
"""

from __future__ import annotations

from lxml import etree

from app.nfe.transporte import ClienteSefaz, RespostaSefaz

NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_SERVICO = "http://www.portalfiscal.inf.br/cte/wsdl/CTeStatusServicoV4"
ACAO = f"{NS_SERVICO}/cteStatusServicoCT"
ELEMENTO_DADOS = "cteDadosMsg"
SOAP_VERSAO = "1.2"
VERSAO = "4.00"


def montar_cons_stat_serv_cte(*, cuf: str, ambiente: str = "2") -> bytes:
    """Monta o `consStatServCTe`.

    O leiaute exige `cUF` (ao contrário do `consStatServ` de NF-e, que usa `xServ` sozinho) —
    descoberto pelo XSD, não por tentativa.
    """
    if len(cuf) != 2 or not cuf.isdigit():
        raise ValueError(f"cUF precisa ter 2 dígitos: {cuf!r}")
    if ambiente not in ("1", "2"):
        raise ValueError(f"ambiente precisa ser '1' (produção) ou '2' (homologação): {ambiente!r}")

    raiz = etree.Element(f"{{{NS_CTE}}}consStatServCTe", nsmap={None: NS_CTE}, versao=VERSAO)
    etree.SubElement(raiz, f"{{{NS_CTE}}}tpAmb").text = ambiente
    etree.SubElement(raiz, f"{{{NS_CTE}}}cUF").text = cuf
    etree.SubElement(raiz, f"{{{NS_CTE}}}xServ").text = "STATUS"
    return b'<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(raiz)


async def consultar_status(
    sefaz: ClienteSefaz, *, url: str, cuf: str, ambiente: str = "2"
) -> RespostaSefaz:
    """Consulta o status do serviço de CT-e. `url` vem do catálogo, nunca de literal aqui."""
    return await sefaz.chamar(
        url=url,
        xml_fiscal=montar_cons_stat_serv_cte(cuf=cuf, ambiente=ambiente),
        ns_servico=NS_SERVICO,
        soap_versao=SOAP_VERSAO,
        elemento_dados=ELEMENTO_DADOS,
    )
