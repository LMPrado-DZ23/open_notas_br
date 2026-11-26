"""Consulta de situação do CT-e (`CTeConsultaV4`).

Valores do WSDL do serviço, medidos com chamada real:

| Item | Valor |
|---|---|
| namespace | `http://www.portalfiscal.inf.br/cte/wsdl/CTeConsultaV4` |
| SOAPAction | `.../CTeConsultaV4/cteConsultaCT` |
| wrapper | `cteDadosMsg` |
| SOAP | 1.2 |

Medido: com chave fictícia o SVRS responde `236 — Chave de Acesso inválida`, ou seja, **a
mensagem foi aceita e chegou à validação fiscal** — que é o que se quer provar sem uma nota real.

Diferença em relação ao status: a consulta exige `chCTe` (a chave), e `cUF` **não** entra.
"""

from __future__ import annotations

from lxml import etree

from app.nfe.transporte import ClienteSefaz, RespostaSefaz

NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_SERVICO = "http://www.portalfiscal.inf.br/cte/wsdl/CTeConsultaV4"
ACAO = f"{NS_SERVICO}/cteConsultaCT"
ELEMENTO_DADOS = "cteDadosMsg"
SOAP_VERSAO = "1.2"
VERSAO = "4.00"


def montar_cons_sit_cte(*, chave: str, ambiente: str = "2") -> bytes:
    """Monta o `consSitCTe` para uma chave de 44 dígitos."""
    if len(chave) != 44 or not chave.isdigit():
        raise ValueError(f"chave do CT-e precisa ter 44 dígitos: {chave!r}")
    if ambiente not in ("1", "2"):
        raise ValueError(f"ambiente precisa ser '1' ou '2': {ambiente!r}")

    raiz = etree.Element(f"{{{NS_CTE}}}consSitCTe", nsmap={None: NS_CTE}, versao=VERSAO)
    etree.SubElement(raiz, f"{{{NS_CTE}}}tpAmb").text = ambiente
    etree.SubElement(raiz, f"{{{NS_CTE}}}xServ").text = "CONSULTAR"
    etree.SubElement(raiz, f"{{{NS_CTE}}}chCTe").text = chave
    return b'<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(raiz)


async def consultar_situacao(
    sefaz: ClienteSefaz, *, url: str, chave: str, ambiente: str = "2"
) -> RespostaSefaz:
    """Consulta uma chave. `url` vem do catálogo, nunca de literal aqui."""
    return await sefaz.chamar(
        url=url,
        xml_fiscal=montar_cons_sit_cte(chave=chave, ambiente=ambiente),
        ns_servico=NS_SERVICO,
        soap_versao=SOAP_VERSAO,
        elemento_dados=ELEMENTO_DADOS,
    )
