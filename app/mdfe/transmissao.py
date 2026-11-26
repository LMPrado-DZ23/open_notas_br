"""Transmissão do MDF-e (`MDFeRecepcaoSinc`).

| Item | Valor (do WSDL) |
|---|---|
| namespace | `http://www.portalfiscal.inf.br/mdfe/wsdl/MDFeRecepcaoSinc` |
| SOAPAction | `.../MDFeRecepcaoSinc/mdfeRecepcao` |
| wrapper | `mdfeDadosMsg` |
| SOAP | 1.2 |

**Não chamado contra a SEFAZ**: emitir documento exige credenciamento e autorização do dono.
"""

from __future__ import annotations

from app.nfe.transporte import ClienteSefaz, RespostaSefaz

NS_MDFE = "http://www.portalfiscal.inf.br/mdfe"
NS_SERVICO = "http://www.portalfiscal.inf.br/mdfe/wsdl/MDFeRecepcaoSinc"
ACAO = f"{NS_SERVICO}/mdfeRecepcao"
ELEMENTO_DADOS = "mdfeDadosMsg"
SOAP_VERSAO = "1.2"


async def enviar(sefaz: ClienteSefaz, *, url: str, mdfe_assinado: bytes) -> RespostaSefaz:
    """Envia um MDF-e já assinado. `url` vem do catálogo."""
    if b"<Signature" not in mdfe_assinado:
        raise ValueError("MDF-e precisa estar assinado antes do envio")
    return await sefaz.chamar(
        url=url,
        xml_fiscal=mdfe_assinado,
        ns_servico=NS_SERVICO,
        soap_versao=SOAP_VERSAO,
        elemento_dados=ELEMENTO_DADOS,
    )
