"""Transmissão do CT-e (`CTeRecepcaoSincV4`) — a recepção síncrona da versão 4.00.

Parâmetros tirados do **WSDL do serviço** (HTTP 200 com mTLS), não de memória:

| Item | Valor |
|---|---|
| namespace | `http://www.portalfiscal.inf.br/cte/wsdl/CTeRecepcaoSincV4` |
| SOAPAction | `.../CTeRecepcaoSincV4/cteRecepcao` |
| wrapper | `cteDadosMsg` |
| SOAP | 1.2 |

**Não chamado contra a SEFAZ**: transmitir aqui é emitir documento, e o dono do projeto autorizou
apenas leitura (status/consulta). O transporte fica pronto para o dia do credenciamento.

Nota de versão: a `RetRecepcao` do fluxo assíncrono da 3.00 não existe em 4.00 — a recepção é
síncrona e devolve o protocolo na mesma resposta (auditoria §35).
"""

from __future__ import annotations

from app.nfe.transporte import ClienteSefaz, RespostaSefaz

NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_SERVICO = "http://www.portalfiscal.inf.br/cte/wsdl/CTeRecepcaoSincV4"
ACAO = f"{NS_SERVICO}/cteRecepcao"
ELEMENTO_DADOS = "cteDadosMsg"
SOAP_VERSAO = "1.2"


async def enviar(sefaz: ClienteSefaz, *, url: str, cte_assinado: bytes) -> RespostaSefaz:
    """Envia um CT-e já assinado. `url` vem do catálogo; nenhum literal de endereço aqui."""
    if b"<Signature" not in cte_assinado:
        # A SEFAZ recusa CT-e sem assinatura; falhar aqui dá erro claro antes da rede.
        raise ValueError("CT-e precisa estar assinado antes do envio")
    return await sefaz.chamar(
        url=url,
        xml_fiscal=cte_assinado,
        ns_servico=NS_SERVICO,
        soap_versao=SOAP_VERSAO,
        elemento_dados=ELEMENTO_DADOS,
    )
